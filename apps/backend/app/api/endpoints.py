import base64
import json
import os
import re
import uuid
import time
import logging
import httpx
from typing import Optional, List, Literal
import redis.asyncio as redis
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from googleapiclient.errors import HttpError as DriveHttpError
from google.auth.exceptions import RefreshError

from app.schemas.requests import (
    ScanRequest,
    FolderIndexRequest,
    PublicSearchRequest,
    PublicSearchResponse,
    SearchMatchResponse,
    FolderResponse,
)
from app.services.drive_service import (
    list_drive_files,
    list_public_drive_folder,
    extract_folder_id,
    get_drive_service,
)
from app.services.ai_service import get_face_encodings
from app.services.embedding_store import embedding_store
from app.services.image_cache_service import IMAGE_CACHE_HEADERS, image_cache_service
from app.workers.tasks import (
    SCAN_EVENT_LUA,
    SCAN_STATUS_TTL,
    FOLDER_INDEX_TTL,
    process_image,
    index_drive_file,
    scan_event_keys,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_image_headers(
    file_id: str,
    download: bool = False,
) -> dict[str, str]:
    headers = dict(IMAGE_CACHE_HEADERS)
    if download:
        raw_name = embedding_store.get_file_name(file_id) or f"{file_id}.jpg"
        safe_name = os.path.basename(raw_name).replace('"', "").replace("\r", "").replace("\n", "")
        headers["Content-Disposition"] = f'attachment; filename="{safe_name}"'
    return headers

@router.get("/folders", response_model=List[FolderResponse])
async def list_folders():
    return embedding_store.list_folders()

@router.get("/folders/{folder_id}", response_model=FolderResponse)
async def get_folder(folder_id: str):
    folder = embedding_store.get_folder(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder

@router.post("/folders/index")
async def index_folder(request: FolderIndexRequest):
    try:
        folder_id = extract_folder_id(request.drive_link)
        access_token = (request.access_token or "").strip() or None

        if access_token:
            service = get_drive_service(access_token)
            try:
                folder_meta = service.files().get(fileId=folder_id, fields="name").execute()
                folder_name = folder_meta.get("name", f"Drive Album {folder_id[:8]}")
            except Exception:
                folder_name = f"Drive Album {folder_id[:8]}"
            files = list_drive_files(request.drive_link, access_token)
        else:
            folder_name, files = list_public_drive_folder(request.drive_link)

        if not files:
            raise HTTPException(status_code=404, detail="No images found in the specified Google Drive folder")

        embedding_store.create_or_update_folder(
            folder_id=folder_id,
            name=folder_name,
            drive_folder_id=folder_id,
            access_token=access_token,
            status="indexing",
            photo_count=len(files),
            faces_count=0,
        )
        embedding_store.reset_folder_faces(folder_id)

        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            counter_key = f"folder_remaining:{folder_id}"
            processed_key = f"folder_processed:{folder_id}"
            await redis_client.delete(processed_key)
            await redis_client.set(counter_key, len(files), ex=FOLDER_INDEX_TTL)
        finally:
            await redis_client.aclose()

        for file in files:
            index_drive_file.delay(
                folder_id=folder_id,
                file_id=file["id"],
                file_name=file.get("name", ""),
                access_token=access_token,
                download_url=file.get("webContentLink"),
                thumbnail_url=file.get("thumbnailLink"),
            )

        return {
            "folder_id": folder_id,
            "folder_name": folder_name,
            "message": f"Queued indexing of {len(files)} photos from '{folder_name}'. Faces will be indexed in background.",
            "total_files": len(files),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except RefreshError:
        raise HTTPException(status_code=401, detail="Google authentication expired")
    except DriveHttpError as e:
        raise HTTPException(status_code=e.status_code, detail=f"Google Drive error: {e.reason}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in index_folder: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/folders/{folder_id}/search", response_model=PublicSearchResponse)
async def search_folder_faces(
    folder_id: str,
    request: PublicSearchRequest,
    background_tasks: BackgroundTasks,
):
    folder = embedding_store.get_folder(folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    start_time = time.time()
    try:
        raw_target = request.target_face.split(",", 1)[1] if "," in request.target_face else request.target_face
        image_data = base64.b64decode(raw_target)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Base64 target face string")

    target_encodings = await run_in_threadpool(get_face_encodings, image_data)
    if not target_encodings:
        raise HTTPException(status_code=400, detail="No face detected in reference photo")

    matches_data = embedding_store.search_faces(
        folder_id=folder_id,
        target_encoding=target_encodings[0],
        tolerance=request.tolerance,
    )

    elapsed_ms = int((time.time() - start_time) * 1000)
    matches = [
        SearchMatchResponse(
            file_id=m["file_id"],
            file_name=m["file_name"],
            confidence=m["confidence"],
            download_url=m.get("download_url"),
            thumbnail_url=m.get("thumbnail_url"),
        )
        for m in matches_data
    ]

    if settings.PREWARM_THUMBNAILS_ON_SEARCH and matches:
        background_tasks.add_task(
            image_cache_service.prewarm_variants,
            [m.file_id for m in matches[:24]],
            embedding_store.get_file_access_token,
            "thumb",
        )

    return PublicSearchResponse(
        folder_id=folder_id,
        total_photos=folder["photo_count"],
        matches=matches,
        elapsed_ms=elapsed_ms,
    )

@router.post("/scan")
async def start_scan(request: ScanRequest):
    try:
        try:
            image_data = base64.b64decode(request.target_face)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid Base64 string")

        target_encodings = await run_in_threadpool(get_face_encodings, image_data)
        if not target_encodings:
            raise HTTPException(status_code=400, detail="No face detected in target image")

        target_encoding_list = target_encodings[0].tolist()
        files = list_drive_files(request.drive_link, request.access_token)
        if not files:
            raise HTTPException(status_code=404, detail="No images found in Drive folder")

        scan_id = str(uuid.uuid4())
        redis_counter_key = f"scan_remaining:{scan_id}"

        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        await redis_client.set(redis_counter_key, len(files), ex=SCAN_STATUS_TTL)
        event_keys = scan_event_keys(scan_id)
        await redis_client.eval(
            SCAN_EVENT_LUA,
            len(event_keys),
            *event_keys,
            json.dumps({
                "type": "started",
                "scan_id": scan_id,
                "total_files": len(files),
            }),
            SCAN_STATUS_TTL,
        )
        await redis_client.aclose()

        for file in files:
            process_image.delay(
                file_id=file["id"],
                file_name=file.get("name", ""),
                access_token=request.access_token,
                target_encoding_list=target_encoding_list,
                scan_id=scan_id,
            )

        return {"message": "Scan started", "total_files": len(files), "scan_id": scan_id}

    except RefreshError:
        raise HTTPException(status_code=401, detail="Google authentication expired.")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DriveHttpError as e:
        raise HTTPException(status_code=e.status_code, detail=f"Google Drive error: {e.reason}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scan/{scan_id}/status")
async def get_scan_status(scan_id: str):
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        status, remaining_str, sequence_str = await redis_client.mget(
            f"scan_status:{scan_id}",
            f"scan_remaining:{scan_id}",
            f"scan_sequence:{scan_id}",
        )
        last_sequence = int(sequence_str) if sequence_str is not None else 0
        if status in {"completed", "token_expired", "failed"}:
            return {
                "scan_id": scan_id,
                "status": status,
                "remaining": 0,
                "last_sequence": last_sequence,
            }
        if remaining_str is not None:
            return {
                "scan_id": scan_id,
                "status": "running",
                "remaining": int(remaining_str),
                "last_sequence": last_sequence,
            }
        return {"scan_id": scan_id, "status": "unknown", "last_sequence": last_sequence}
    finally:
        await redis_client.aclose()

@router.get("/drive/image/{file_id}")
async def get_drive_image(
    file_id: str,
    access_token: Optional[str] = None,
    size: Literal["full", "thumb", "preview"] = Query("full"),
    download: bool = Query(False),
):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", file_id):
        raise HTTPException(status_code=400, detail="Invalid file ID")

    effective_token = (access_token or "").strip() or embedding_store.get_file_access_token(file_id)
    response_headers = _build_image_headers(file_id, download=download)

    if size in ("thumb", "preview"):
        cached_path = await image_cache_service.get_or_fetch_variant(
            file_id=file_id,
            variant=size,
            access_token=effective_token,
        )
        if cached_path is not None:
            return FileResponse(
                cached_path,
                media_type="image/jpeg",
                headers=response_headers,
            )

    client = httpx.AsyncClient(follow_redirects=True, timeout=30.0)
    response = None

    try:
        if effective_token:
            api_url = settings.DRIVE_API_FILE_MEDIA_URL.format(file_id=file_id)
            req = client.build_request("GET", api_url, headers={"Authorization": f"Bearer {effective_token}"})
            response = await client.send(req, stream=True)
            if response.status_code != 200:
                await response.aclose()
                response = None

        if response is None:
            public_url = settings.DRIVE_PUBLIC_DOWNLOAD_URL.format(file_id=file_id)
            req = client.build_request("GET", public_url)
            response = await client.send(req, stream=True)

        content_type = response.headers.get("content-type", "image/jpeg").lower()
        if response.status_code != 200 or content_type.startswith("text/html"):
            status = 401 if content_type.startswith("text/html") else response.status_code
            await response.aclose()
            await client.aclose()
            raise HTTPException(status_code=status, detail="Failed to fetch image from Drive")

        async def stream_chunks():
            async for chunk in response.aiter_bytes():
                yield chunk

        async def close_stream():
            await response.aclose()
            await client.aclose()

        return StreamingResponse(
            stream_chunks(),
            media_type=content_type.split(";", 1)[0],
            headers=response_headers,
            background=BackgroundTask(close_stream),
        )
    except HTTPException:
        raise
    except Exception as exc:
        if response is not None:
            await response.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Failed to fetch image from Drive: {exc}")

@router.websocket("/ws/updates/{scan_id}")
async def websocket_endpoint(websocket: WebSocket, scan_id: str, after_sequence: int = 0):
    await websocket.accept()
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = redis_client.pubsub()
    channel = f"scan_updates:{scan_id}"
    last_sequence = max(0, after_sequence)

    try:
        await pubsub.subscribe(channel)
        while True:
            subscription = await pubsub.get_message(
                ignore_subscribe_messages=False,
                timeout=5.0,
            )
            if subscription is None:
                raise TimeoutError(f"Timed out subscribing to {channel}")
            if (
                subscription["type"] == "subscribe"
                and subscription["channel"] == channel
            ):
                break

        persisted_events = await redis_client.lrange(f"scan_events:{scan_id}", 0, -1)
        for encoded_event in persisted_events:
            event = json.loads(encoded_event)
            sequence = int(event["sequence"])
            if sequence > last_sequence:
                await websocket.send_text(encoded_event)
                last_sequence = sequence

        async for message in pubsub.listen():
            if message["type"] == "message":
                event = json.loads(message["data"])
                sequence = int(event["sequence"])
                if sequence > last_sequence:
                    await websocket.send_text(message["data"])
                    last_sequence = sequence
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.warning(f"WebSocket error: {e}")
    finally:
        await pubsub.unsubscribe(channel)
        await redis_client.aclose()

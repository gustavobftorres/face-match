import base64
import json
import uuid
import asyncio
import logging
import httpx
import redis.asyncio as redis
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from googleapiclient.errors import HttpError as DriveHttpError
from app.schemas.requests import ScanRequest
from app.services.drive_service import list_drive_files
from app.services.ai_service import get_face_encodings
from app.workers.tasks import (
    SCAN_EVENT_LUA,
    SCAN_STATUS_TTL,
    process_image,
    scan_event_keys,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

from google.auth.exceptions import RefreshError

@router.post("/scan")
async def start_scan(request: ScanRequest):
    logger.info(f"Received scan request for drive link: {request.drive_link}")
    try:
        try:
            image_data = base64.b64decode(request.target_face)
            logger.info("Successfully decoded base64 target face image")
        except Exception:
            logger.error("Failed to decode base64 string")
            raise HTTPException(status_code=400, detail="Invalid Base64 string")

        target_encodings = get_face_encodings(image_data)
        if not target_encodings:
            logger.warning("No face detected in the provided target image")
            raise HTTPException(status_code=400, detail="No face detected in target image")

        logger.info(f"Detected {len(target_encodings)} face(s) in target image")
        target_encoding_list = target_encodings[0].tolist()

        logger.info("Listing files from Google Drive...")
        files = list_drive_files(request.drive_link, request.access_token)
        if not files:
            logger.warning("No images found in the specified Drive folder")
            raise HTTPException(status_code=404, detail="No images found in Drive folder")
        
        logger.info(f"Found {len(files)} images in Drive folder. Starting processing tasks...")

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
        
        logger.info(f"Dispatched {len(files)} tasks to Celery worker (scan_id={scan_id})")
        return {"message": "Scan started", "total_files": len(files), "scan_id": scan_id}

    except RefreshError:
        logger.warning("Google Drive token invalid or expired")
        raise HTTPException(status_code=401, detail="Google authentication expired. Please refresh the page and login again.")
    except ValueError as e:
        logger.warning(f"Invalid drive link: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except DriveHttpError as e:
        logger.error(f"Google Drive API error: {e.status_code} — {e.reason}")
        raise HTTPException(status_code=e.status_code, detail=f"Google Drive error: {e.reason}")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Unexpected error in start_scan: {str(e)}")
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
async def get_drive_image(file_id: str, access_token: str):
    url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    async def stream_image():
        async with httpx.AsyncClient(follow_redirects=True) as client:
            async with client.stream("GET", url, headers=headers) as response:
                if response.status_code != 200:
                    logger.error(f"Failed to fetch image {file_id}. Status: {response.status_code}")
                    raise HTTPException(status_code=response.status_code, detail="Failed to fetch image from Drive")
                
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream_image(), media_type="image/jpeg")


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

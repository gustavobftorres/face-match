import httpx
import redis
import json
import numpy as np
import logging
from io import BytesIO
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded, Retry
from app.core.celery_app import celery_app
from app.core.config import settings
from app.services.ai_service import get_face_encodings, compare_faces

logger = logging.getLogger(__name__)

redis_text_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

DOWNLOAD_TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=15.0, pool=15.0)
MAX_RETRIES = 3
SCAN_STATUS_TTL = 3600


def publish(payload: dict):
    redis_text_client.publish("scan_updates", json.dumps(payload))


def persist_scan_completion(scan_id: str):
    redis_text_client.setex(f"scan_status:{scan_id}", SCAN_STATUS_TTL, "completed")


def decrement_and_check_completion(scan_id: str, dedup_key: str):
    if not scan_id:
        return
    redis_counter_key = f"scan_remaining:{scan_id}"
    remaining = redis_text_client.decr(redis_counter_key)
    logger.info(f"[scan_id={scan_id}] Files remaining: {remaining}")
    if remaining <= 0:
        logger.info(f"[scan_id={scan_id}] All files processed. Publishing completed event.")
        persist_scan_completion(scan_id)
        publish({"type": "completed", "scan_id": scan_id})
        redis_text_client.delete(redis_counter_key)
        redis_text_client.delete(dedup_key)


def download_file(file_id: str, access_token: str) -> bytes:
    headers = {"Authorization": f"Bearer {access_token}"}
    download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    buffer = BytesIO()
    with httpx.stream("GET", download_url, headers=headers, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            buffer.write(chunk)
    return buffer.getvalue()


@celery_app.task(bind=True, max_retries=MAX_RETRIES)
def process_image(self: Task, file_id: str, file_name: str, access_token: str, target_encoding_list: list, scan_id: str = ""):
    dedup_key = f"scan_processed:{scan_id}"
    already_processed = scan_id and not redis_text_client.sadd(dedup_key, file_id)
    if already_processed:
        logger.warning(f"[scan_id={scan_id}] Skipping duplicate task for file {file_id}")
        return

    logger.info(f"Processing file: {file_name} (ID: {file_id})")

    should_decrement = True

    try:
        logger.info(f"Downloading file {file_id}...")

        try:
            image_content = download_file(file_id, access_token)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.error(f"Download failed for {file_id}: HTTP {status_code}")
            if status_code == 401:
                logger.error("Token expired. Purging remaining tasks and notifying frontend.")
                publish({"type": "token_expired", "message": "Google token expired. Please re-authenticate and restart the scan."})
                celery_app.control.purge()
                redis_text_client.srem(dedup_key, file_id)
                should_decrement = False
            else:
                publish({"type": "error", "file_id": file_id, "file_name": file_name, "error": f"Download failed: HTTP {status_code}"})
            return

        except httpx.TransportError as exc:
            error_type = type(exc).__name__
            attempt = self.request.retries + 1
            logger.warning(f"Transport error ({error_type}) downloading {file_id} (attempt {attempt}/{MAX_RETRIES + 1}): {exc}")
            if self.request.retries < MAX_RETRIES:
                should_decrement = False
                redis_text_client.srem(dedup_key, file_id)
                raise self.retry(exc=exc, countdown=2 ** self.request.retries)
            logger.error(f"All retries exhausted for {file_id} after {error_type}. Marking as error.")
            publish({"type": "error", "file_id": file_id, "file_name": file_name, "error": f"Network error after {MAX_RETRIES} retries: {error_type}"})
            return

        logger.info(f"File {file_id} downloaded. Processing...")
        unknown_encodings = get_face_encodings(image_content)

        if not unknown_encodings:
            logger.info(f"No face found in file {file_id}")
            publish({"type": "progress", "file_id": file_id, "file_name": file_name, "status": "no_face_found"})
            return

        logger.info(f"Found {len(unknown_encodings)} face(s) in file {file_id}. Comparing...")
        target_encoding = np.array(target_encoding_list)
        match_found = any(compare_faces(target_encoding, enc) for enc in unknown_encodings)

        result_status = "match" if match_found else "no_match"
        logger.info(f"Comparison result for {file_id}: {result_status}")

        publish({
            "type": "match" if match_found else "progress",
            "file_id": file_id,
            "file_name": file_name,
            "status": result_status,
            "download_url": f"https://drive.google.com/uc?id={file_id}&export=download" if match_found else None,
        })

    except Retry:
        raise

    except SoftTimeLimitExceeded:
        logger.error(f"Soft time limit exceeded for file {file_id}. Marking as error.")
        publish({"type": "error", "file_id": file_id, "file_name": file_name, "error": "Processing timed out"})

    except Exception as e:
        logger.error(f"Error processing file {file_id}: {str(e)}")
        publish({"type": "error", "file_id": file_id, "file_name": file_name, "error": str(e)})

    finally:
        if should_decrement:
            decrement_and_check_completion(scan_id, dedup_key)

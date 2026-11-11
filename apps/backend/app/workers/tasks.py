import httpx
import redis
import json
import numpy as np
import logging
import math
import uuid
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
MAX_COORDINATION_RETRIES = 3
SCAN_STATUS_TTL = 3600
CLAIM_TTL = 480


SCAN_EVENT_LUA = """
local sequence = redis.call('INCR', KEYS[1])
local event = cjson.decode(ARGV[1])
event['sequence'] = sequence
local encoded = cjson.encode(event)
redis.call('RPUSH', KEYS[2], encoded)
redis.call('PUBLISH', KEYS[3], encoded)
local ttl = tonumber(ARGV[2])
for index = 1, #KEYS do
    if index ~= 3 then
        redis.call('EXPIRE', KEYS[index], ttl)
    end
end
return encoded
"""

CLAIM_FILE_LUA = """
local status = redis.call('GET', KEYS[6])
if status == 'completed' or status == 'token_expired' or status == 'failed' then
    return 2
end
if redis.call('EXISTS', KEYS[3]) == 0 then
    return -2
end
if tonumber(redis.call('GET', KEYS[3])) <= 0 then
    return 0
end
if redis.call('SISMEMBER', KEYS[1], ARGV[1]) == 1 then
    return 0
end
local claimed = redis.call('SET', KEYS[2], ARGV[2], 'NX', 'EX', tonumber(ARGV[3]))
if not claimed then
    return -1
end
local ttl = tonumber(ARGV[4])
for index = 1, #KEYS do
    if index ~= 2 then
        redis.call('EXPIRE', KEYS[index], ttl)
    end
end
return 1
"""

RELEASE_CLAIM_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""

FINALIZE_FILE_LUA = """
local ttl = tonumber(ARGV[3])
if redis.call('EXISTS', KEYS[1]) == 0 then
    return {'missing_counter', ''}
end
local current = tonumber(redis.call('GET', KEYS[1]))
if current <= 0 then
    return {'exhausted_counter', tostring(current)}
end
if redis.call('SISMEMBER', KEYS[3], ARGV[1]) == 1 then
    return {'duplicate', tostring(current)}
end

local function publish_event(raw_event)
    local sequence = redis.call('INCR', KEYS[4])
    local event = cjson.decode(raw_event)
    event['sequence'] = sequence
    local encoded = cjson.encode(event)
    redis.call('RPUSH', KEYS[5], encoded)
    redis.call('PUBLISH', KEYS[6], encoded)
end

local status = redis.call('GET', KEYS[2])
redis.call('SADD', KEYS[3], ARGV[1])
local remaining = redis.call('DECR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ttl)
redis.call('EXPIRE', KEYS[3], ttl)

if status ~= 'completed' and status ~= 'token_expired' and status ~= 'failed' and ARGV[2] ~= '' then
    publish_event(ARGV[2])
end

if remaining == 0 and not status then
    local completed = redis.call('SET', KEYS[2], 'completed', 'NX', 'EX', ttl)
    if completed then
        publish_event(cjson.encode({type = 'completed', scan_id = ARGV[4]}))
        status = 'completed'
    end
end

redis.call('EXPIRE', KEYS[2], ttl)
redis.call('EXPIRE', KEYS[4], ttl)
redis.call('EXPIRE', KEYS[5], ttl)
return {status or 'running', tostring(remaining)}
"""

TOKEN_EXPIRED_LUA = """
local ttl = tonumber(ARGV[3])
if redis.call('EXISTS', KEYS[1]) == 0 then
    return {'missing_counter', ''}
end
local current = tonumber(redis.call('GET', KEYS[1]))
if current <= 0 then
    return {'exhausted_counter', tostring(current)}
end
if redis.call('SISMEMBER', KEYS[3], ARGV[1]) == 1 then
    return {'duplicate', tostring(current)}
end

local function publish_event(raw_event)
    local sequence = redis.call('INCR', KEYS[4])
    local event = cjson.decode(raw_event)
    event['sequence'] = sequence
    local encoded = cjson.encode(event)
    redis.call('RPUSH', KEYS[5], encoded)
    redis.call('PUBLISH', KEYS[6], encoded)
end

local first_expiration = redis.call('SET', KEYS[2], 'token_expired', 'NX', 'EX', ttl)
if first_expiration then
    publish_event(ARGV[2])
end
redis.call('SADD', KEYS[3], ARGV[1])
local remaining = redis.call('DECR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ttl)
redis.call('EXPIRE', KEYS[2], ttl)
redis.call('EXPIRE', KEYS[3], ttl)
redis.call('EXPIRE', KEYS[4], ttl)
redis.call('EXPIRE', KEYS[5], ttl)
return {first_expiration and 'token_expired' or 'terminal_exists', tostring(remaining)}
"""

FAIL_SCAN_LUA = """
local ttl = tonumber(ARGV[2])
local failed = redis.call('SET', KEYS[1], 'failed', 'NX', 'EX', ttl)
if not failed then
    return redis.call('GET', KEYS[1]) or 'terminal_exists'
end
local sequence = redis.call('INCR', KEYS[2])
local event = cjson.decode(ARGV[1])
event['sequence'] = sequence
local encoded = cjson.encode(event)
redis.call('RPUSH', KEYS[3], encoded)
redis.call('PUBLISH', KEYS[4], encoded)
redis.call('EXPIRE', KEYS[2], ttl)
redis.call('EXPIRE', KEYS[3], ttl)
return 'failed'
"""


def scan_event_keys(scan_id: str):
    return (
        f"scan_sequence:{scan_id}",
        f"scan_events:{scan_id}",
        f"scan_updates:{scan_id}",
        f"scan_remaining:{scan_id}",
        f"scan_status:{scan_id}",
        f"scan_processed:{scan_id}",
    )


def finalize_file(scan_id: str, file_id: str, payload: dict | None):
    keys = (
        f"scan_remaining:{scan_id}",
        f"scan_status:{scan_id}",
        f"scan_processed:{scan_id}",
        f"scan_sequence:{scan_id}",
        f"scan_events:{scan_id}",
        f"scan_updates:{scan_id}",
    )
    encoded = json.dumps({**payload, "scan_id": scan_id}) if payload else ""
    return redis_text_client.eval(
        FINALIZE_FILE_LUA,
        len(keys),
        *keys,
        file_id,
        encoded,
        SCAN_STATUS_TTL,
        scan_id,
    )


def expire_token_and_finalize(scan_id: str, file_id: str):
    keys = (
        f"scan_remaining:{scan_id}",
        f"scan_status:{scan_id}",
        f"scan_processed:{scan_id}",
        f"scan_sequence:{scan_id}",
        f"scan_events:{scan_id}",
        f"scan_updates:{scan_id}",
    )
    payload = json.dumps({
        "type": "token_expired",
        "scan_id": scan_id,
        "message": "Google token expired. Please re-authenticate and restart the scan.",
    })
    return redis_text_client.eval(
        TOKEN_EXPIRED_LUA,
        len(keys),
        *keys,
        file_id,
        payload,
        SCAN_STATUS_TTL,
    )


def fail_scan(scan_id: str, error: str):
    keys = (
        f"scan_status:{scan_id}",
        f"scan_sequence:{scan_id}",
        f"scan_events:{scan_id}",
        f"scan_updates:{scan_id}",
    )
    payload = json.dumps({
        "type": "error",
        "scan_id": scan_id,
        "status": "failed",
        "error": error,
    })
    return redis_text_client.eval(
        FAIL_SCAN_LUA,
        len(keys),
        *keys,
        payload,
        SCAN_STATUS_TTL,
    )


def download_file(file_id: str, access_token: str) -> bytes:
    headers = {"Authorization": f"Bearer {access_token}"}
    download_url = f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"
    buffer = BytesIO()
    with httpx.stream("GET", download_url, headers=headers, follow_redirects=True, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            buffer.write(chunk)
    return buffer.getvalue()


@celery_app.task(bind=True, max_retries=None)
def process_image(
    self: Task,
    file_id: str,
    file_name: str,
    access_token: str,
    target_encoding_list: list,
    scan_id: str,
    transport_attempt: int = 0,
    coordination_attempt: int = 0,
):
    claim_token = str(uuid.uuid4())
    claim_key = f"scan_claim:{scan_id}:{file_id}"
    claim_keys = (
        f"scan_processed:{scan_id}",
        claim_key,
        f"scan_remaining:{scan_id}",
        f"scan_sequence:{scan_id}",
        f"scan_events:{scan_id}",
        f"scan_status:{scan_id}",
    )
    claim_result = redis_text_client.eval(
        CLAIM_FILE_LUA,
        len(claim_keys),
        *claim_keys,
        file_id,
        claim_token,
        CLAIM_TTL,
        SCAN_STATUS_TTL,
    )
    if claim_result == 0:
        logger.warning(f"[scan_id={scan_id}] Skipping already processed file {file_id}")
        return
    if claim_result == -2:
        if coordination_attempt >= MAX_COORDINATION_RETRIES:
            error = f"Scan state expired before file {file_id} could be processed"
            logger.error(f"[scan_id={scan_id}] {error}; marking scan as failed")
            fail_scan(scan_id, error)
            return
        countdown = min(2 ** coordination_attempt, 60)
        logger.error(
            f"[scan_id={scan_id}] Missing counter for file {file_id}; "
            f"coordination retry {coordination_attempt + 1}/{MAX_COORDINATION_RETRIES} "
            f"in {countdown}s"
        )
        retry_kwargs = dict(self.request.kwargs or {})
        retry_kwargs["transport_attempt"] = transport_attempt
        retry_kwargs["coordination_attempt"] = coordination_attempt + 1
        raise self.retry(
            exc=RuntimeError(f"Missing scan counter for {scan_id}"),
            countdown=countdown,
            kwargs=retry_kwargs,
        )
    if claim_result == 2:
        finalize_file(scan_id, file_id, None)
        return
    if claim_result == -1:
        claim_pttl = redis_text_client.pttl(claim_key)
        countdown = (
            max(1, math.ceil(claim_pttl / 1000))
            if claim_pttl > 0
            else min(2 ** min(coordination_attempt, 6), 60)
        )
        logger.info(
            f"[scan_id={scan_id}] File {file_id} is already in flight; "
            f"coordination retry in {countdown}s (claim pttl={claim_pttl}ms)"
        )
        retry_kwargs = dict(self.request.kwargs or {})
        retry_kwargs["transport_attempt"] = transport_attempt
        retry_kwargs["coordination_attempt"] = coordination_attempt + 1
        raise self.retry(
            exc=RuntimeError(f"File {file_id} is already in flight"),
            countdown=countdown,
            kwargs=retry_kwargs,
        )

    logger.info(f"Processing file: {file_name} (ID: {file_id})")

    try:
        logger.info(f"Downloading file {file_id}...")

        try:
            image_content = download_file(file_id, access_token)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            logger.error(f"Download failed for {file_id}: HTTP {status_code}")
            if status_code == 401:
                logger.error("Token expired. Marking only this scan as expired and notifying frontend.")
                expire_token_and_finalize(scan_id, file_id)
            else:
                finalize_file(scan_id, file_id, {
                    "type": "error",
                    "file_id": file_id,
                    "file_name": file_name,
                    "error": f"Download failed: HTTP {status_code}",
                })
            return

        except httpx.TransportError as exc:
            error_type = type(exc).__name__
            attempt = transport_attempt + 1
            logger.warning(f"Transport error ({error_type}) downloading {file_id} (attempt {attempt}/{MAX_RETRIES + 1}): {exc}")
            if transport_attempt < MAX_RETRIES:
                retry_kwargs = dict(self.request.kwargs or {})
                retry_kwargs["transport_attempt"] = transport_attempt + 1
                retry_kwargs["coordination_attempt"] = coordination_attempt
                raise self.retry(
                    exc=exc,
                    countdown=2 ** transport_attempt,
                    kwargs=retry_kwargs,
                )
            logger.error(f"All retries exhausted for {file_id} after {error_type}. Marking as error.")
            finalize_file(scan_id, file_id, {
                "type": "error",
                "file_id": file_id,
                "file_name": file_name,
                "error": f"Network error after {MAX_RETRIES} retries: {error_type}",
            })
            return

        logger.info(f"File {file_id} downloaded. Processing...")
        unknown_encodings = get_face_encodings(image_content)

        if not unknown_encodings:
            logger.info(f"No face found in file {file_id}")
            finalize_file(scan_id, file_id, {
                "type": "progress",
                "file_id": file_id,
                "file_name": file_name,
                "status": "no_face_found",
            })
            return

        logger.info(f"Found {len(unknown_encodings)} face(s) in file {file_id}. Comparing...")
        target_encoding = np.array(target_encoding_list)
        match_found = any(compare_faces(target_encoding, enc) for enc in unknown_encodings)

        result_status = "match" if match_found else "no_match"
        logger.info(f"Comparison result for {file_id}: {result_status}")

        finalize_file(scan_id, file_id, {
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
        finalize_file(scan_id, file_id, {
            "type": "error",
            "file_id": file_id,
            "file_name": file_name,
            "error": "Processing timed out",
        })

    except Exception as e:
        logger.error(f"Error processing file {file_id}: {str(e)}")
        finalize_file(scan_id, file_id, {
            "type": "error",
            "file_id": file_id,
            "file_name": file_name,
            "error": str(e),
        })

    finally:
        redis_text_client.eval(RELEASE_CLAIM_LUA, 1, claim_key, claim_token)

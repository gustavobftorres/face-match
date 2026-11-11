# workers

Celery task definitions for asynchronous image processing.

## Architecture

- `tasks.py` — The `process_image` Celery task. Downloads an image from Google
  Drive, extracts face encodings, compares against the target face, and records
  and publishes scan-scoped events through Redis.

## Data Flow

```
Celery Queue → process_image task
  → download_file() [streaming, up to 3 retries on timeout]
  → get_face_encodings() [PIL decode + max 1000 px + face_recognition]
  → compare_faces() [distance < 0.6 threshold]
  → finalize_file() [atomic dedup + decrement + sequenced event]
  → RPUSH scan_events:<scan_id> + PUBLISH scan_updates:<scan_id>
```

## Reliability

- **Timeout retries:** `httpx.TimeoutException` triggers up to 3 retries with exponential backoff (`2^n` seconds).
- **HTTP 401:** Token expiry atomically marks only that scan as
  `token_expired`; later work sees the terminal state and does not emit normal
  results.
- **Task limits:** The `360 s` soft limit is handled as a per-file `error`; the
  `420 s` hard limit is the final worker safeguard.
- **Claim and dedup guards:** `scan_claim:<scan_id>:<file_id>` prevents
  concurrent processing while `scan_processed:<scan_id>` prevents a file from
  decrementing the counter twice.
- **Atomic finalization:** Lua scripts mark a file processed, decrement its
  scan's remaining counter, assign the next sequence, persist the event, and
  publish it as one Redis operation.
- **Terminal state:** The last file emits `completed`. Exhausted coordination
  retries emit a scan-level error and set `failed`. Workers stop normal event
  publication after `completed`, `token_expired`, or `failed`.
- **Replay:** `scan_events:<scan_id>` retains ordered event JSON for WebSocket
  replay. State and history use a one-hour TTL.

## Config

Controlled via `app/core/celery_app.py`:
- `worker_max_tasks_per_child=50` — prevents memory growth on large scans.
- `worker_prefetch_multiplier=1` — prevents task pile-up in memory.
- `task_acks_late=True` — re-queues tasks if the worker dies mid-execution.
- `task_soft_time_limit=360` — raises `SoftTimeLimitExceeded` for cleanup.
- `task_time_limit=420` — hard-kills a task that exceeds the final limit.

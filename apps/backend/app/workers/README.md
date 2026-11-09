# workers

Celery task definitions for asynchronous image processing.

## Architecture

- `tasks.py` — The `process_image` Celery task. Downloads an image from Google Drive, extracts face encodings, compares against the target face, and publishes results to a Redis pub/sub channel.

## Data Flow

```
Celery Queue → process_image task
  → download_file() [streaming, up to 3 retries on timeout]
  → get_face_encodings() [PIL decode + face_recognition small model]
  → compare_faces() [distance < 0.45 threshold]
  → redis_client.publish("scan_updates", event_json)
  → decrement_and_check_completion() [always runs via finally]
```

## Reliability

- **Timeout retries:** `httpx.TimeoutException` triggers up to 3 retries with exponential backoff (`2^n` seconds).
- **HTTP 401:** Token expiry purges all remaining queued tasks and emits a `token_expired` event.
- **Soft time limit:** Tasks killed after 180 s emit an `error` event and still decrement the scan counter.
- **Dedup guard:** `scan_processed:<scan_id>` Redis set prevents a task from being processed twice.
- **Completion guarantee:** `decrement_and_check_completion` runs inside a `finally` block — it fires regardless of success, error, or timeout.

## Config

Controlled via `app/core/celery_app.py`:
- `worker_max_tasks_per_child=50` — prevents memory growth on large scans.
- `worker_prefetch_multiplier=1` — prevents task pile-up in memory.
- `task_acks_late=True` — re-queues tasks if the worker dies mid-execution.

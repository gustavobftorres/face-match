# core

Application-wide configuration and Celery worker initialization.

## Files

### `config.py`
Pydantic `Settings` class loaded from `.env`. Exposes:
- `REDIS_URL` — broker and backend for Celery.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` — OAuth credentials.
- `API_V1_STR` — API path prefix.
- `ALLOWED_ORIGINS` — CORS origin whitelist.

### `celery_app.py`
Creates and configures the shared `celery_app` instance.

**Key settings:**

| Setting                     | Value | Effect                                                      |
|-----------------------------|-------|-------------------------------------------------------------|
| `worker_prefetch_multiplier`| `1`   | Each worker only holds 1 task at a time — no pile-up        |
| `worker_max_tasks_per_child`| `50`  | Worker process is recycled after 50 tasks — prevents memory growth |
| `task_acks_late`            | `True`| Task is only ack'd after completion — re-queued if worker crashes |
| `task_reject_on_worker_lost`| `True`| Pairs with `task_acks_late` to ensure re-queue on crash     |
| `task_soft_time_limit`      | `180` | Raises `SoftTimeLimitExceeded` after 180 s — allows cleanup |
| `task_time_limit`           | `240` | Hard kills the task after 240 s — last resort               |

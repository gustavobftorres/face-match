# core

Application-wide configuration and Celery worker initialization.

## Files

### `config.py`
Pydantic `Settings` class loaded from repository-root and backend `.env` / `.env.local` files. Exposes:
- `REDIS_URL` — broker and backend for Celery.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` — OAuth credentials.
- `DATABASE_URL` — pooled Neon Postgres connection string for runtime queries.
- `DATABASE_URL_UNPOOLED` — direct unpooled Postgres connection string for schema DDL and bulk migrations.
- `FACE_MATCH_DB_PATH` — fallback SQLite path when `DATABASE_URL` is unset or explicitly overridden.
- `API_V1_STR` — API path prefix.
- `ALLOWED_ORIGINS` — CORS origin whitelist.
- `THUMBNAIL_CACHE_DIR` — disk directory caching generated `thumb` and `preview` JPEG files.
- `PREWARM_THUMBNAILS_ON_SEARCH` — toggles background warming of matched photo thumbnails after `/search`.
- `DRIVE_EMBEDDED_FOLDER_URL`, `DRIVE_PUBLIC_FILE_VIEW_URL`, `DRIVE_PUBLIC_DOWNLOAD_URL`, `DRIVE_PUBLIC_UC_DOWNLOAD_URL`, `DRIVE_PUBLIC_THUMBNAIL_URL`, `DRIVE_FAST_THUMBNAIL_URL`, `DRIVE_THUMBNAIL_SIZE_URL`, `DRIVE_API_FILE_MEDIA_URL` — centralized Google Drive endpoint templates.

### `celery_app.py`
Creates and configures the shared `celery_app` instance.

**Key settings:**

| Setting                     | Value | Effect                                                      |
|-----------------------------|-------|-------------------------------------------------------------|
| `worker_prefetch_multiplier`| `1`   | Each worker only holds 1 task at a time — no pile-up        |
| `worker_max_tasks_per_child`| `50`  | Worker process is recycled after 50 tasks — prevents memory growth |
| `task_acks_late`            | `True`| Task is only ack'd after completion — re-queued if worker crashes |
| `task_reject_on_worker_lost`| `True`| Pairs with `task_acks_late` to ensure re-queue on crash     |
| `task_soft_time_limit`      | `360` | Raises `SoftTimeLimitExceeded` after 360 s — allows cleanup |
| `task_time_limit`           | `420` | Hard kills the task after 420 s — last resort               |

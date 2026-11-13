# services

## Purpose
Business logic for interacting with Google Drive, computing facial embeddings, and managing persistent embedding storage.

## Files

### `drive_service.py`
Extracts folder IDs from Google Drive URLs or bare IDs, lists images via OAuth Drive API v3 when `access_token` is supplied, and parses public embedded Google Drive folder views when `access_token` is omitted.

### `ai_service.py`
Handles image decoding and face recognition using `face_recognition` and `dlib`.
- `get_face_encodings(image_content: bytes) -> list`: Extracts 128-d face encodings.
- `compare_faces(known_encoding, unknown_encoding) -> bool`: Computes Euclidean distance below 0.6 threshold.

### `postgres_embedding_store.py`
Neon Postgres (`pgvector` / `lakebase_vector`) storage backend implementing folder metadata persistence and in-database L2 (`<->`) vector distance search.
- Uses `DATABASE_URL_UNPOOLED` for extension/table/index initialization and `DATABASE_URL` (pooled via `psycopg_pool` with `prepare_threshold=None` and fork-safe lazy initialization) for runtime queries.
- Filters matching embeddings directly inside Postgres (`(encoding <-> target::vector) <= tolerance`) to minimize network egress.

### `embedding_store.py`
Storage facade (`EmbeddingStore` and singleton `embedding_store`) plus `SQLiteEmbeddingStore` fallback:
- Selects `PostgresEmbeddingStore` when `DATABASE_URL` is configured (unless an explicit SQLite `db_path` is passed, e.g. in isolated unit tests).
- `create_or_update_folder`: Persists album metadata and indexing status.
- `delete_folder`: Deletes an indexed folder and cascades its face rows.
- `reset_folder_faces`: Clears existing embeddings when re-indexing an album.
- `save_face_encodings`: Idempotently stores face encodings per `(folder_id, file_id)` and keeps `faces_count` synchronized.
- `search_faces`: Performs vector distance search against stored folder embeddings.
- `get_file_access_token`: Resolves saved album tokens to stream images when authentication is required.
- `get_file_name`: Resolves the indexed original file name for download `Content-Disposition` headers.

### `image_cache_service.py`
Disk-backed async thumbnail cache and connection-pooled Drive image fetcher:
- `get_or_fetch_variant`: Serves `thumb` (`480px`) or `preview` (`1080px`) JPEG variants from disk (`THUMBNAIL_CACHE_DIR`) or fetches/resizes atomically on cache miss with per-file in-flight locks.
- `cache_thumbnail_from_bytes`: Generates and persists local `thumb` JPEG files directly during Celery folder indexing.
- `prewarm_variants`: Concurrently warms cached thumbnails for matched search results in background tasks.

# Backend Tests

## Purpose
Automated test suite verifying facial recognition logic, Celery scan isolation, public Google Drive indexing, thumbnail caching, and SQLite / Neon Postgres embedding storage.

## Structure
- `evaluation/`: Tests for offline evaluation metrics and benchmark evaluation pipelines.
- `scan/`: Integration and unit tests for concurrency, state locking, and Redis event coordination.
- `test_embedding_store.py`: Unit tests for SQLite persistent embedding storage and vector face matching.
- `test_postgres_embedding_store.py`: Unit and optional live integration tests for Neon Postgres (`pgvector` / `lakebase_vector`) embedding storage and backend selection.
- `test_public_drive_indexing.py`: End-to-end mocked tests for public Google Drive folder parsing, indexing, image streaming, and face search.
- `test_image_cache.py`: Unit tests for cached thumbnail/preview generation and download headers.

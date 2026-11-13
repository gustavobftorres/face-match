# scripts

Utility scripts for operational maintenance and data migrations.

## Files

### `migrate_sqlite_to_neon.py`
Idempotently migrates folders and 128-d face embeddings from the local SQLite database (`FACE_MATCH_DB_PATH`) into Neon Postgres (`DATABASE_URL_UNPOOLED` for schema/bulk writes, `DATABASE_URL` for pooled runtime queries), converting BLOB float64 arrays into `pgvector` `vector(128)` values.

**Usage:**
```bash
cd apps/backend
venv/bin/python scripts/migrate_sqlite_to_neon.py
```

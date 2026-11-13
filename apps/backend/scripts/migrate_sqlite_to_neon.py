import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import psycopg

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
from app.services.postgres_embedding_store import PostgresEmbeddingStore, vector_to_pg_literal


def _read_sqlite_data(db_path: str) -> Tuple[List[Tuple], List[Tuple]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        folders = conn.execute(
            """
            SELECT id, name, drive_folder_id, access_token, photo_count, faces_count, status, indexed_at
            FROM folders
            ORDER BY indexed_at ASC
            """
        ).fetchall()
        faces = conn.execute(
            """
            SELECT id, folder_id, file_id, file_name, download_url, thumbnail_url, encoding
            FROM faces
            """
        ).fetchall()
        folder_rows = [
            (
                row["id"],
                row["name"],
                row["drive_folder_id"],
                row["access_token"],
                row["photo_count"],
                row["faces_count"],
                row["status"],
                row["indexed_at"],
            )
            for row in folders
        ]
        face_rows = [
            (
                row["id"],
                row["folder_id"],
                row["file_id"],
                row["file_name"],
                row["download_url"],
                row["thumbnail_url"],
                vector_to_pg_literal(np.frombuffer(row["encoding"], dtype=np.float64)),
            )
            for row in faces
        ]
        return folder_rows, face_rows
    finally:
        conn.close()


def migrate_sqlite_to_postgres(
    sqlite_path: str,
    database_url: str,
    unpooled_database_url: Optional[str] = None,
    batch_size: int = 250,
) -> Dict[str, int]:
    effective_unpooled = (unpooled_database_url or database_url).strip()
    if not effective_unpooled:
        raise ValueError("Missing Postgres connection URL")

    store = PostgresEmbeddingStore(
        database_url=database_url or effective_unpooled,
        unpooled_database_url=effective_unpooled,
    )
    store.init_db()

    folder_rows, face_rows = _read_sqlite_data(sqlite_path)

    with psycopg.connect(effective_unpooled, prepare_threshold=None) as conn:
        with conn.cursor() as cur:
            if folder_rows:
                cur.executemany(
                    """
                    INSERT INTO folders (id, name, drive_folder_id, access_token, photo_count, faces_count, status, indexed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        drive_folder_id = EXCLUDED.drive_folder_id,
                        access_token = COALESCE(EXCLUDED.access_token, folders.access_token),
                        photo_count = EXCLUDED.photo_count,
                        faces_count = EXCLUDED.faces_count,
                        status = EXCLUDED.status,
                        indexed_at = EXCLUDED.indexed_at
                    """,
                    folder_rows,
                )

            for start in range(0, len(face_rows), batch_size):
                batch = face_rows[start : start + batch_size]
                cur.executemany(
                    """
                    INSERT INTO faces (id, folder_id, file_id, file_name, download_url, thumbnail_url, encoding)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                    ON CONFLICT (id) DO UPDATE SET
                        folder_id = EXCLUDED.folder_id,
                        file_id = EXCLUDED.file_id,
                        file_name = EXCLUDED.file_name,
                        download_url = EXCLUDED.download_url,
                        thumbnail_url = EXCLUDED.thumbnail_url,
                        encoding = EXCLUDED.encoding
                    """,
                    batch,
                )

            cur.execute(
                """
                UPDATE folders
                SET faces_count = (
                    SELECT COUNT(*) FROM faces WHERE faces.folder_id = folders.id
                )
                """
            )
        conn.commit()

    with psycopg.connect(effective_unpooled, autocommit=True, prepare_threshold=None) as conn:
        conn.execute("ANALYZE folders")
        conn.execute("ANALYZE faces")
        counts = conn.execute(
            "SELECT (SELECT COUNT(*) FROM folders), (SELECT COUNT(*) FROM faces), (SELECT COUNT(DISTINCT file_id) FROM faces)"
        ).fetchone()

    store.close()
    return {
        "source_folders": len(folder_rows),
        "source_faces": len(face_rows),
        "target_folders": int(counts[0]),
        "target_faces": int(counts[1]),
        "target_distinct_files": int(counts[2]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite face embeddings to Neon Postgres")
    parser.add_argument("--sqlite-path", default=settings.FACE_MATCH_DB_PATH)
    parser.add_argument("--database-url", default=settings.DATABASE_URL)
    parser.add_argument("--unpooled-url", default=settings.DATABASE_URL_UNPOOLED)
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()

    stats = migrate_sqlite_to_postgres(
        sqlite_path=args.sqlite_path,
        database_url=args.database_url,
        unpooled_database_url=args.unpooled_url,
        batch_size=args.batch_size,
    )
    print(stats)


if __name__ == "__main__":
    main()

import os
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import psycopg
from psycopg_pool import ConnectionPool


def vector_to_pg_literal(encoding: np.ndarray) -> str:
    arr = np.asarray(encoding, dtype=np.float64).ravel()
    return "[" + ",".join(repr(float(v)) for v in arr) + "]"


def pg_literal_to_vector(value: Union[str, Sequence[float], np.ndarray]) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return value.astype(np.float64, copy=False)
    if isinstance(value, str):
        stripped = value.strip().strip("[]")
        if not stripped:
            return np.array([], dtype=np.float64)
        return np.fromstring(stripped, sep=",", dtype=np.float64)
    return np.asarray(value, dtype=np.float64)


def compute_confidence(distance: float, tolerance: float) -> float:
    if tolerance <= 0:
        return 1.0 if distance <= 0 else 0.0
    return max(0.0, round(float(1.0 - (distance / tolerance) * 0.45), 3))


def _row_to_folder(row: Sequence[Any]) -> Dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "drive_folder_id": row[2],
        "access_token": row[3],
        "photo_count": row[4],
        "faces_count": row[5],
        "status": row[6],
        "indexed_at": row[7],
    }


def _row_to_folder_summary(row: Sequence[Any]) -> Dict[str, Any]:
    return {
        "id": row[0],
        "name": row[1],
        "drive_folder_id": row[2],
        "photo_count": row[3],
        "faces_count": row[4],
        "status": row[5],
        "indexed_at": row[6],
    }


class PostgresEmbeddingStore:
    def __init__(self, database_url: str, unpooled_database_url: Optional[str] = None):
        self.database_url = database_url.strip()
        self.unpooled_database_url = (unpooled_database_url or database_url).strip()
        self._pool: Optional[ConnectionPool] = None
        self._pool_pid: Optional[int] = None
        self._pool_lock = threading.Lock()
        self._schema_initialized = False
        self._schema_lock = threading.Lock()

    def init_db(self) -> None:
        self._ensure_schema()

    def close(self) -> None:
        with self._pool_lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None
                self._pool_pid = None

    def _ensure_schema(self) -> None:
        if self._schema_initialized:
            return
        with self._schema_lock:
            if self._schema_initialized:
                return
            with psycopg.connect(
                self.unpooled_database_url,
                autocommit=True,
                prepare_threshold=None,
            ) as conn:
                has_lakebase = True
                try:
                    conn.execute("CREATE EXTENSION IF NOT EXISTS lakebase_vector CASCADE")
                except (psycopg.errors.FeatureNotSupported, psycopg.errors.UndefinedFile):
                    has_lakebase = False
                    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS folders (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        drive_folder_id TEXT NOT NULL,
                        access_token TEXT,
                        photo_count INTEGER NOT NULL DEFAULT 0,
                        faces_count INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'ready',
                        indexed_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS faces (
                        id TEXT PRIMARY KEY,
                        folder_id TEXT NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
                        file_id TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        download_url TEXT,
                        thumbnail_url TEXT,
                        encoding vector(128) NOT NULL
                    )
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_faces_folder ON faces(folder_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_faces_file ON faces(file_id)")
                if has_lakebase:
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_faces_encoding_ann ON faces USING lakebase_ann (encoding vector_l2_ops)"
                    )
            self._schema_initialized = True

    def _get_pool(self) -> ConnectionPool:
        current_pid = os.getpid()
        if self._pool is not None and self._pool_pid == current_pid:
            return self._pool
        with self._pool_lock:
            if self._pool is not None and self._pool_pid != current_pid:
                self._pool = None
            if self._pool is None:
                self._pool = ConnectionPool(
                    self.database_url,
                    min_size=0,
                    max_size=5,
                    max_idle=300.0,
                    check=ConnectionPool.check_connection,
                    kwargs={"prepare_threshold": None},
                    open=True,
                )
                self._pool_pid = current_pid
            return self._pool

    @contextmanager
    def _connection(self):
        self._ensure_schema()
        pool = self._get_pool()
        with pool.connection() as conn:
            yield conn

    def create_or_update_folder(
        self,
        folder_id: str,
        name: str,
        drive_folder_id: str,
        access_token: Optional[str] = None,
        status: str = "indexing",
        photo_count: int = 0,
        faces_count: int = 0,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
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
                    (folder_id, name, drive_folder_id, access_token, photo_count, faces_count, status, now),
                )
            conn.commit()
        folder = self.get_folder(folder_id)
        assert folder is not None
        return folder

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, drive_folder_id, access_token, photo_count, faces_count, status, indexed_at
                    FROM folders
                    WHERE id = %s
                    """,
                    (folder_id,),
                )
                row = cur.fetchone()
        return _row_to_folder(row) if row else None

    def list_folders(self) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, drive_folder_id, photo_count, faces_count, status, indexed_at
                    FROM folders
                    ORDER BY indexed_at DESC
                    """
                )
                rows = cur.fetchall()
        return [_row_to_folder_summary(row) for row in rows]

    def delete_folder(self, folder_id: str) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM folders WHERE id = %s", (folder_id,))
            conn.commit()

    def reset_folder_faces(self, folder_id: str) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM faces WHERE folder_id = %s", (folder_id,))
                cur.execute("UPDATE folders SET faces_count = 0 WHERE id = %s", (folder_id,))
            conn.commit()

    def save_face_encodings(
        self,
        folder_id: str,
        file_id: str,
        file_name: str,
        encodings: List[np.ndarray],
        download_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
    ) -> int:
        rows = [
            (
                str(uuid.uuid4()),
                folder_id,
                file_id,
                file_name,
                download_url,
                thumbnail_url,
                vector_to_pg_literal(encoding),
            )
            for encoding in encodings
        ]
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM faces WHERE folder_id = %s AND file_id = %s",
                    (folder_id, file_id),
                )
                if rows:
                    cur.executemany(
                        """
                        INSERT INTO faces (id, folder_id, file_id, file_name, download_url, thumbnail_url, encoding)
                        VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                        """,
                        rows,
                    )
                cur.execute(
                    "UPDATE folders SET faces_count = (SELECT COUNT(*) FROM faces WHERE folder_id = %s) WHERE id = %s",
                    (folder_id, folder_id),
                )
            conn.commit()
        return len(encodings)

    def update_folder_status(self, folder_id: str, status: str, photo_count: Optional[int] = None) -> None:
        with self._connection() as conn:
            with conn.cursor() as cur:
                if photo_count is not None:
                    cur.execute(
                        "UPDATE folders SET status = %s, photo_count = %s WHERE id = %s",
                        (status, photo_count, folder_id),
                    )
                else:
                    cur.execute(
                        "UPDATE folders SET status = %s WHERE id = %s",
                        (status, folder_id),
                    )
            conn.commit()

    def get_folder_faces(self, folder_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, file_id, file_name, download_url, thumbnail_url, encoding::text
                    FROM faces
                    WHERE folder_id = %s
                    """,
                    (folder_id,),
                )
                rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "file_id": row[1],
                "file_name": row[2],
                "download_url": row[3],
                "thumbnail_url": row[4],
                "encoding": pg_literal_to_vector(row[5]),
            }
            for row in rows
        ]

    def get_file_access_token(self, file_id: str) -> Optional[str]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT fo.access_token
                    FROM faces fa
                    JOIN folders fo ON fa.folder_id = fo.id
                    WHERE fa.file_id = %s AND fo.access_token IS NOT NULL
                    LIMIT 1
                    """,
                    (file_id,),
                )
                row = cur.fetchone()
        return row[0] if row else None

    def get_file_name(self, file_id: str) -> Optional[str]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT file_name FROM faces WHERE file_id = %s LIMIT 1",
                    (file_id,),
                )
                row = cur.fetchone()
        return row[0] if row else None

    def search_faces(self, folder_id: str, target_encoding: np.ndarray, tolerance: float = 0.6) -> List[Dict[str, Any]]:
        if tolerance < 0:
            return []
        target_literal = vector_to_pg_literal(target_encoding)
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT file_id, file_name, download_url, thumbnail_url, (encoding <-> %s::vector) AS distance
                    FROM faces
                    WHERE folder_id = %s
                      AND (encoding <-> %s::vector) <= %s
                    ORDER BY distance ASC
                    """,
                    (target_literal, folder_id, target_literal, float(tolerance)),
                )
                rows = cur.fetchall()
        best_by_file: Dict[str, Dict[str, Any]] = {}
        for file_id, file_name, download_url, thumbnail_url, distance in rows:
            confidence = compute_confidence(float(distance), float(tolerance))
            if file_id not in best_by_file or confidence > best_by_file[file_id]["confidence"]:
                best_by_file[file_id] = {
                    "file_id": file_id,
                    "file_name": file_name,
                    "download_url": download_url,
                    "thumbnail_url": thumbnail_url,
                    "confidence": confidence,
                }
        results = list(best_by_file.values())
        results.sort(key=lambda item: item["confidence"], reverse=True)
        return results

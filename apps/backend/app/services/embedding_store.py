import sqlite3
import uuid
import datetime
from typing import List, Dict, Any, Optional
import numpy as np
from app.core.config import settings
from app.services.postgres_embedding_store import PostgresEmbeddingStore

DB_PATH = settings.FACE_MATCH_DB_PATH

class SQLiteEmbeddingStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def init_db(self) -> None:
        self._init_db()

    def close(self) -> None:
        return None

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS folders (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    drive_folder_id TEXT NOT NULL,
                    access_token TEXT,
                    photo_count INTEGER DEFAULT 0,
                    faces_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'ready',
                    indexed_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faces (
                    id TEXT PRIMARY KEY,
                    folder_id TEXT NOT NULL,
                    file_id TEXT NOT NULL,
                    file_name TEXT NOT NULL,
                    download_url TEXT,
                    thumbnail_url TEXT,
                    encoding BLOB NOT NULL,
                    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_faces_folder ON faces(folder_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_faces_file ON faces(file_id)"
            )
            conn.commit()

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
        indexed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self._get_connection() as conn:
            existing = conn.execute(
                "SELECT * FROM folders WHERE id = ?", (folder_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE folders 
                    SET name = ?, drive_folder_id = ?, access_token = coalesce(?, access_token), 
                        status = ?, photo_count = ?, faces_count = ?, indexed_at = ?
                    WHERE id = ?
                    """,
                    (name, drive_folder_id, access_token, status, photo_count, faces_count, indexed_at, folder_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO folders (id, name, drive_folder_id, access_token, photo_count, faces_count, status, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (folder_id, name, drive_folder_id, access_token, photo_count, faces_count, status, indexed_at),
                )
            conn.commit()
        return self.get_folder(folder_id) or {}

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM folders WHERE id = ?", (folder_id,)
            ).fetchone()
            if not row:
                return None
            return dict(row)

    def list_folders(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, name, drive_folder_id, photo_count, faces_count, status, indexed_at FROM folders ORDER BY indexed_at DESC"
            ).fetchall()
            return [dict(row) for row in rows]

    def reset_folder_faces(self, folder_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM faces WHERE folder_id = ?", (folder_id,))
            conn.execute(
                "UPDATE folders SET faces_count = 0 WHERE id = ?",
                (folder_id,),
            )
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
        with self._get_connection() as conn:
            conn.execute(
                "DELETE FROM faces WHERE folder_id = ? AND file_id = ?",
                (folder_id, file_id),
            )
            for enc in encodings:
                face_id = str(uuid.uuid4())
                enc_bytes = np.asarray(enc, dtype=np.float64).tobytes()
                conn.execute(
                    """
                    INSERT INTO faces (id, folder_id, file_id, file_name, download_url, thumbnail_url, encoding)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (face_id, folder_id, file_id, file_name, download_url, thumbnail_url, enc_bytes),
                )
            conn.execute(
                """
                UPDATE folders
                SET faces_count = (SELECT COUNT(*) FROM faces WHERE folder_id = ?)
                WHERE id = ?
                """,
                (folder_id, folder_id),
            )
            conn.commit()
        return len(encodings)

    def update_folder_status(
        self, folder_id: str, status: str, photo_count: Optional[int] = None
    ) -> None:
        with self._get_connection() as conn:
            if photo_count is not None:
                conn.execute(
                    "UPDATE folders SET status = ?, photo_count = ? WHERE id = ?",
                    (status, photo_count, folder_id),
                )
            else:
                conn.execute(
                    "UPDATE folders SET status = ? WHERE id = ?",
                    (status, folder_id),
                )
            conn.commit()

    def get_folder_faces(self, folder_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, file_id, file_name, download_url, thumbnail_url, encoding FROM faces WHERE folder_id = ?",
                (folder_id,),
            ).fetchall()
            results = []
            for row in rows:
                enc_arr = np.frombuffer(row["encoding"], dtype=np.float64)
                results.append({
                    "id": row["id"],
                    "file_id": row["file_id"],
                    "file_name": row["file_name"],
                    "download_url": row["download_url"],
                    "thumbnail_url": row["thumbnail_url"],
                    "encoding": enc_arr,
                })
            return results

    def get_file_access_token(self, file_id: str) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT f.access_token 
                FROM folders f 
                JOIN faces fa ON f.id = fa.folder_id 
                WHERE fa.file_id = ? 
                LIMIT 1
                """,
                (file_id,),
            ).fetchone()
            if row and row["access_token"]:
                return row["access_token"]
            return None

    def get_file_name(self, file_id: str) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT file_name FROM faces WHERE file_id = ? LIMIT 1",
                (file_id,),
            ).fetchone()
            if row and row["file_name"]:
                return row["file_name"]
            return None

    def search_faces(
        self, folder_id: str, target_encoding: np.ndarray, tolerance: float = 0.6
    ) -> List[Dict[str, Any]]:
        if tolerance <= 0:
            return []
        faces = self.get_folder_faces(folder_id)
        if not faces:
            return []

        encodings_matrix = np.array([f["encoding"] for f in faces])
        target_vec = np.asarray(target_encoding, dtype=np.float64)
        distances = np.linalg.norm(encodings_matrix - target_vec, axis=1)

        best_matches_by_file: Dict[str, Dict[str, Any]] = {}
        for idx, dist in enumerate(distances):
            if dist <= tolerance:
                f = faces[idx]
                file_id = f["file_id"]
                confidence = max(0.0, round(float(1.0 - (dist / tolerance) * 0.45), 3))
                if file_id not in best_matches_by_file or confidence > best_matches_by_file[file_id]["confidence"]:
                    best_matches_by_file[file_id] = {
                        "file_id": file_id,
                        "file_name": f["file_name"],
                        "confidence": confidence,
                        "download_url": f["download_url"],
                        "thumbnail_url": f["thumbnail_url"],
                    }

        sorted_matches = sorted(
            best_matches_by_file.values(), key=lambda x: x["confidence"], reverse=True
        )
        return sorted_matches

    def delete_folder(self, folder_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
            conn.commit()


class EmbeddingStore:
    def __init__(
        self,
        db_path: Optional[str] = None,
        database_url: Optional[str] = None,
        unpooled_database_url: Optional[str] = None,
    ):
        effective_database_url = (
            database_url
            if database_url is not None
            else (settings.DATABASE_URL if db_path is None else "")
        )
        effective_unpooled_url = (
            unpooled_database_url
            if unpooled_database_url is not None
            else (settings.DATABASE_URL_UNPOOLED if db_path is None else "")
        )
        if db_path is None and effective_database_url:
            self._backend = PostgresEmbeddingStore(
                database_url=effective_database_url,
                unpooled_database_url=effective_unpooled_url or None,
            )
            self.db_path = None
        else:
            resolved_path = db_path or settings.FACE_MATCH_DB_PATH
            self._backend = SQLiteEmbeddingStore(db_path=resolved_path)
            self.db_path = resolved_path

    def init_db(self) -> None:
        self._backend.init_db()

    def close(self) -> None:
        self._backend.close()

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
        return self._backend.create_or_update_folder(
            folder_id=folder_id,
            name=name,
            drive_folder_id=drive_folder_id,
            access_token=access_token,
            status=status,
            photo_count=photo_count,
            faces_count=faces_count,
        )

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        return self._backend.get_folder(folder_id)

    def list_folders(self) -> List[Dict[str, Any]]:
        return self._backend.list_folders()

    def delete_folder(self, folder_id: str) -> None:
        self._backend.delete_folder(folder_id)

    def reset_folder_faces(self, folder_id: str) -> None:
        self._backend.reset_folder_faces(folder_id)

    def save_face_encodings(
        self,
        folder_id: str,
        file_id: str,
        file_name: str,
        encodings: List[np.ndarray],
        download_url: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
    ) -> int:
        return self._backend.save_face_encodings(
            folder_id=folder_id,
            file_id=file_id,
            file_name=file_name,
            encodings=encodings,
            download_url=download_url,
            thumbnail_url=thumbnail_url,
        )

    def update_folder_status(self, folder_id: str, status: str, photo_count: Optional[int] = None) -> None:
        self._backend.update_folder_status(folder_id, status, photo_count=photo_count)

    def get_folder_faces(self, folder_id: str) -> List[Dict[str, Any]]:
        return self._backend.get_folder_faces(folder_id)

    def get_file_access_token(self, file_id: str) -> Optional[str]:
        return self._backend.get_file_access_token(file_id)

    def get_file_name(self, file_id: str) -> Optional[str]:
        return self._backend.get_file_name(file_id)

    def search_faces(self, folder_id: str, target_encoding: np.ndarray, tolerance: float = 0.6) -> List[Dict[str, Any]]:
        return self._backend.search_faces(folder_id, target_encoding, tolerance=tolerance)


embedding_store = EmbeddingStore()

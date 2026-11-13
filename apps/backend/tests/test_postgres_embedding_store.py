import os
import uuid
import numpy as np
import pytest

from app.core.config import settings
from app.services.embedding_store import EmbeddingStore


class FakeCursor:
    def __init__(self, state):
        self.state = state
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        sql = " ".join(query.split())
        self.state["queries"].append((sql, params))
        params = params or ()

        if sql.startswith("INSERT INTO folders"):
            folder_id, name, drive_folder_id, access_token, photo_count, faces_count, status, indexed_at = params
            existing = self.state["folders"].get(folder_id)
            effective_token = access_token if access_token is not None else (existing["access_token"] if existing else None)
            self.state["folders"][folder_id] = {
                "id": folder_id,
                "name": name,
                "drive_folder_id": drive_folder_id,
                "access_token": effective_token,
                "photo_count": photo_count,
                "faces_count": faces_count,
                "status": status,
                "indexed_at": indexed_at,
            }
            self._rows = []
            return

        if sql.startswith("SELECT id, name, drive_folder_id, access_token, photo_count, faces_count, status, indexed_at FROM folders WHERE id = %s"):
            folder = self.state["folders"].get(params[0])
            if folder:
                self._rows = [(
                    folder["id"],
                    folder["name"],
                    folder["drive_folder_id"],
                    folder["access_token"],
                    folder["photo_count"],
                    folder["faces_count"],
                    folder["status"],
                    folder["indexed_at"],
                )]
            else:
                self._rows = []
            return

        if sql.startswith("SELECT id, name, drive_folder_id, photo_count, faces_count, status, indexed_at FROM folders ORDER BY indexed_at DESC"):
            ordered = sorted(self.state["folders"].values(), key=lambda r: r["indexed_at"], reverse=True)
            self._rows = [
                (
                    f["id"],
                    f["name"],
                    f["drive_folder_id"],
                    f["photo_count"],
                    f["faces_count"],
                    f["status"],
                    f["indexed_at"],
                )
                for f in ordered
            ]
            return

        if sql.startswith("DELETE FROM folders WHERE id = %s"):
            folder_id = params[0]
            self.state["folders"].pop(folder_id, None)
            self.state["faces"] = [f for f in self.state["faces"] if f["folder_id"] != folder_id]
            self._rows = []
            return

        if sql.startswith("DELETE FROM faces WHERE folder_id = %s AND file_id = %s"):
            folder_id, file_id = params
            self.state["faces"] = [
                f for f in self.state["faces"] if not (f["folder_id"] == folder_id and f["file_id"] == file_id)
            ]
            self._rows = []
            return

        if sql.startswith("DELETE FROM faces WHERE folder_id = %s"):
            folder_id = params[0]
            self.state["faces"] = [f for f in self.state["faces"] if f["folder_id"] != folder_id]
            self._rows = []
            return

        if sql.startswith("UPDATE folders SET faces_count = 0 WHERE id = %s"):
            folder = self.state["folders"].get(params[0])
            if folder:
                folder["faces_count"] = 0
            self._rows = []
            return

        if sql.startswith("UPDATE folders SET faces_count = (SELECT COUNT(*) FROM faces WHERE folder_id = %s) WHERE id = %s"):
            folder_id = params[1]
            folder = self.state["folders"].get(folder_id)
            if folder:
                folder["faces_count"] = sum(1 for f in self.state["faces"] if f["folder_id"] == folder_id)
            self._rows = []
            return

        if sql.startswith("UPDATE folders SET status = %s, photo_count = %s WHERE id = %s"):
            status, photo_count, folder_id = params
            folder = self.state["folders"].get(folder_id)
            if folder:
                folder["status"] = status
                folder["photo_count"] = photo_count
            self._rows = []
            return

        if sql.startswith("UPDATE folders SET status = %s WHERE id = %s"):
            status, folder_id = params
            folder = self.state["folders"].get(folder_id)
            if folder:
                folder["status"] = status
            self._rows = []
            return

        if sql.startswith("SELECT id, file_id, file_name, download_url, thumbnail_url, encoding::text FROM faces WHERE folder_id = %s"):
            folder_id = params[0]
            self._rows = [
                (
                    f["id"],
                    f["file_id"],
                    f["file_name"],
                    f["download_url"],
                    f["thumbnail_url"],
                    f["encoding"],
                )
                for f in self.state["faces"]
                if f["folder_id"] == folder_id
            ]
            return

        if sql.startswith("SELECT fo.access_token FROM faces fa JOIN folders fo ON fa.folder_id = fo.id"):
            file_id = params[0]
            matches = []
            for face in self.state["faces"]:
                if face["file_id"] == file_id:
                    folder = self.state["folders"].get(face["folder_id"])
                    if folder and folder["access_token"]:
                        matches.append((folder["access_token"],))
                        break
            self._rows = matches
            return

        if sql.startswith("SELECT file_name FROM faces WHERE file_id = %s LIMIT 1"):
            file_id = params[0]
            matches = [(f["file_name"],) for f in self.state["faces"] if f["file_id"] == file_id]
            self._rows = matches[:1]
            return

        if "FROM faces WHERE folder_id = %s AND (encoding <-> %s::vector) <= %s" in sql:
            target_literal, folder_id, _, tolerance = params
            target_vec = np.fromstring(target_literal.strip("[]"), sep=",", dtype=np.float64)
            matches = []
            for face in self.state["faces"]:
                if face["folder_id"] != folder_id:
                    continue
                face_vec = np.fromstring(face["encoding"].strip("[]"), sep=",", dtype=np.float64)
                dist = float(np.linalg.norm(face_vec - target_vec))
                if dist <= float(tolerance):
                    matches.append((
                        face["file_id"],
                        face["file_name"],
                        face["download_url"],
                        face["thumbnail_url"],
                        dist,
                    ))
            matches.sort(key=lambda r: r[4])
            self._rows = matches
            return

        self._rows = []

    def executemany(self, query, param_seq):
        sql = " ".join(query.split())
        self.state["queries"].append((f"MANY:{sql}", len(param_seq)))
        if sql.startswith("INSERT INTO faces"):
            for face_id, folder_id, file_id, file_name, download_url, thumbnail_url, enc_literal in param_seq:
                self.state["faces"].append({
                    "id": face_id,
                    "folder_id": folder_id,
                    "file_id": file_id,
                    "file_name": file_name,
                    "download_url": download_url,
                    "thumbnail_url": thumbnail_url,
                    "encoding": enc_literal,
                })

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConnection:
    def __init__(self, state):
        self.state = state
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return FakeCursor(self.state)

    def execute(self, query, params=None):
        cur = FakeCursor(self.state)
        cur.execute(query, params)
        return cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        return None


class FakePool:
    check_connection = staticmethod(lambda conn: None)

    def __init__(self, conninfo, state, kwargs=None, **pool_opts):
        self.conninfo = conninfo
        self.state = state
        self.kwargs = kwargs or {}
        self.pool_opts = pool_opts
        self.closed = False

    def connection(self):
        return FakeConnection(self.state)

    def close(self):
        self.closed = True


def _unit_vec(index: int, scale: float = 1.0) -> np.ndarray:
    vec = np.zeros(128, dtype=np.float64)
    vec[index] = scale
    return vec


def test_vector_conversion_and_confidence_helpers():
    from app.services.postgres_embedding_store import (
        compute_confidence,
        pg_literal_to_vector,
        vector_to_pg_literal,
    )

    vec = _unit_vec(3, 0.42)
    literal = vector_to_pg_literal(vec)
    assert literal.startswith("[") and literal.endswith("]")
    parsed = pg_literal_to_vector(literal)
    assert parsed.shape == (128,)
    assert np.allclose(parsed, vec)

    assert compute_confidence(0.0, 0.6) == 1.0
    assert compute_confidence(0.3, 0.6) == 0.775
    assert compute_confidence(0.0, 0.0) == 1.0
    assert compute_confidence(0.1, 0.0) == 0.0


def test_embedding_store_selects_backend_correctly(tmp_path, monkeypatch):
    from app.services.postgres_embedding_store import PostgresEmbeddingStore
    from app.services.embedding_store import SQLiteEmbeddingStore

    sqlite_path = str(tmp_path / "explicit.db")
    sqlite_store = EmbeddingStore(db_path=sqlite_path)
    assert isinstance(sqlite_store._backend, SQLiteEmbeddingStore)

    pg_store = EmbeddingStore(
        database_url="postgresql://user:pass@ep-demo-pooler.neon.tech/neondb?sslmode=require",
        unpooled_database_url="postgresql://user:pass@ep-demo.neon.tech/neondb?sslmode=require",
    )
    assert isinstance(pg_store._backend, PostgresEmbeddingStore)


def test_postgres_store_lifecycle_and_pgvector_search(monkeypatch):
    from app.services import postgres_embedding_store as pg_mod

    state = {"folders": {}, "faces": [], "queries": [], "connect_urls": []}

    def fake_connect(url, autocommit=False, **kwargs):
        state["connect_urls"].append(url)
        return FakeConnection(state)

    created_pools = []

    def fake_pool_factory(conninfo, **opts):
        pool = FakePool(conninfo, state, **opts)
        created_pools.append(pool)
        return pool

    fake_pool_factory.check_connection = FakePool.check_connection
    monkeypatch.setattr(pg_mod.psycopg, "connect", fake_connect)
    monkeypatch.setattr(pg_mod, "ConnectionPool", fake_pool_factory)

    pooled_url = "postgresql://user:pass@ep-test-pooler.neon.tech/neondb?sslmode=require"
    unpooled_url = "postgresql://user:pass@ep-test.neon.tech/neondb?sslmode=require"
    store = EmbeddingStore(database_url=pooled_url, unpooled_database_url=unpooled_url)

    assert state["connect_urls"] == []
    assert created_pools == []

    folder = store.create_or_update_folder(
        folder_id="folder-1",
        name="Wedding Album",
        drive_folder_id="drive-1",
        access_token="secret-tok",
        status="indexing",
        photo_count=5,
    )
    assert folder["name"] == "Wedding Album"
    assert state["connect_urls"] == [unpooled_url]
    assert len(created_pools) == 1
    assert created_pools[0].conninfo == pooled_url
    assert created_pools[0].kwargs.get("prepare_threshold") is None

    store.save_face_encodings(
        folder_id="folder-1",
        file_id="img-1",
        file_name="bride.jpg",
        encodings=[_unit_vec(0, 0.1), _unit_vec(0, 0.5)],
        download_url="https://dl/1",
        thumbnail_url="https://thumb/1",
    )
    store.save_face_encodings(
        folder_id="folder-1",
        file_id="img-1",
        file_name="bride.jpg",
        encodings=[_unit_vec(0, 0.05), _unit_vec(1, 0.9)],
        download_url="https://dl/1",
        thumbnail_url="https://thumb/1",
    )
    store.save_face_encodings(
        folder_id="folder-1",
        file_id="img-2",
        file_name="guest.jpg",
        encodings=[_unit_vec(0, 0.35)],
        download_url="https://dl/2",
        thumbnail_url="https://thumb/2",
    )
    store.update_folder_status("folder-1", "ready", photo_count=12)

    listed = store.list_folders()
    assert len(listed) == 1
    assert listed[0]["faces_count"] == 3
    assert listed[0]["photo_count"] == 12
    assert listed[0]["status"] == "ready"
    assert "access_token" not in listed[0]

    assert store.get_file_access_token("img-1") == "secret-tok"
    assert store.get_file_name("img-2") == "guest.jpg"

    matches = store.search_faces("folder-1", _unit_vec(0, 0.0), tolerance=0.6)
    assert [m["file_id"] for m in matches] == ["img-1", "img-2"]
    assert matches[0]["confidence"] > matches[1]["confidence"]

    zero_matches = store.search_faces("folder-1", _unit_vec(0, 0.05), tolerance=0.0)
    assert len(zero_matches) == 1
    assert zero_matches[0]["file_id"] == "img-1"
    assert zero_matches[0]["confidence"] == 1.0

    faces = store.get_folder_faces("folder-1")
    assert len(faces) == 3
    assert isinstance(faces[0]["encoding"], np.ndarray)

    store.reset_folder_faces("folder-1")
    assert store.get_folder("folder-1")["faces_count"] == 0
    assert store.get_folder_faces("folder-1") == []

    store.close()
    assert created_pools[0].closed is True


@pytest.mark.skipif(
    os.getenv("RUN_NEON_INTEGRATION_TESTS") != "1" or not settings.DATABASE_URL,
    reason="Live Neon integration test runs only when RUN_NEON_INTEGRATION_TESTS=1",
)
def test_live_neon_postgres_store_end_to_end():
    store = EmbeddingStore(
        database_url=settings.DATABASE_URL,
        unpooled_database_url=settings.DATABASE_URL_UNPOOLED,
    )
    test_folder_id = f"test-folder-{uuid.uuid4().hex[:8]}"
    try:
        created = store.create_or_update_folder(
            folder_id=test_folder_id,
            name="Neon Integration Album",
            drive_folder_id=test_folder_id,
            access_token="tok-live",
            status="indexing",
            photo_count=2,
        )
        assert created["id"] == test_folder_id
        store.save_face_encodings(
            folder_id=test_folder_id,
            file_id="live-file-1",
            file_name="live.jpg",
            encodings=[_unit_vec(2, 0.1), _unit_vec(2, 0.45)],
            download_url="https://example.com/dl",
            thumbnail_url="https://example.com/thumb",
        )
        store.update_folder_status(test_folder_id, "ready", photo_count=2)
        results = store.search_faces(test_folder_id, _unit_vec(2, 0.08), tolerance=0.6)
        assert len(results) == 1
        assert results[0]["file_id"] == "live-file-1"
        assert results[0]["confidence"] > 0.9
        assert store.get_file_name("live-file-1") == "live.jpg"
        assert store.get_file_access_token("live-file-1") == "tok-live"
    finally:
        store.delete_folder(test_folder_id)
        store.close()

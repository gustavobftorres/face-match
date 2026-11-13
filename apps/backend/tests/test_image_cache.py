from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api import endpoints
from app.main import app
from app.services.embedding_store import EmbeddingStore
from app.services.image_cache_service import ImageCacheService


def _make_jpeg_bytes(width: int = 1200, height: int = 800) -> bytes:
    image = Image.new("RGB", (width, height), color=(230, 81, 26))
    buf = BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    store = EmbeddingStore(db_path=str(tmp_path / "cache_test.db"))
    cache = ImageCacheService(cache_dir=str(tmp_path / "cache"))
    monkeypatch.setattr(endpoints, "embedding_store", store)
    monkeypatch.setattr(endpoints, "image_cache_service", cache)
    monkeypatch.setattr(endpoints.settings, "PREWARM_THUMBNAILS_ON_SEARCH", False)
    return store, cache


def test_cache_thumbnail_from_bytes_resizes_and_persists(tmp_path):
    cache = ImageCacheService(cache_dir=str(tmp_path / "thumbs"))
    raw = _make_jpeg_bytes(width=1600, height=1200)

    saved = cache.cache_thumbnail_from_bytes("FILE_123", raw, variant="thumb")

    assert saved is not None
    assert saved.is_file()
    with Image.open(saved) as thumb:
        assert max(thumb.size) == 480


def test_drive_image_thumb_caches_and_hits_disk_on_repeat_request(isolated_env, monkeypatch):
    store, cache = isolated_env
    store.create_or_update_folder(
        folder_id="album-1",
        name="Siqui",
        drive_folder_id="album-1",
        access_token=None,
        status="ready",
        photo_count=1,
    )
    store.save_face_encodings(
        folder_id="album-1",
        file_id="THUMB_FILE_1",
        file_name="party_shot.jpg",
        encodings=[np.ones(128, dtype=np.float64) * 0.3],
    )

    thumb_bytes = _make_jpeg_bytes(width=480, height=320)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/jpeg"}
    mock_response.content = thumb_bytes

    mock_client = MagicMock()
    mock_client.is_closed = False
    mock_client.get = AsyncMock(return_value=mock_response)
    monkeypatch.setattr(cache, "get_http_client", lambda: mock_client)

    client = TestClient(app)
    first = client.get("/api/v1/drive/image/THUMB_FILE_1?size=thumb")
    second = client.get("/api/v1/drive/image/THUMB_FILE_1?size=thumb")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == thumb_bytes
    assert second.content == thumb_bytes
    assert "max-age=604800" in first.headers["cache-control"]
    assert mock_client.get.await_count == 1


def test_drive_image_download_param_sets_content_disposition(isolated_env, monkeypatch):
    store, _cache = isolated_env
    store.create_or_update_folder(
        folder_id="album-dl",
        name="Album DL",
        drive_folder_id="album-dl",
        access_token=None,
        status="ready",
        photo_count=1,
    )
    store.save_face_encodings(
        folder_id="album-dl",
        file_id="FULL_FILE_1",
        file_name="273A7563.jpg",
        encodings=[np.ones(128, dtype=np.float64) * 0.2],
    )

    full_bytes = _make_jpeg_bytes(width=800, height=600)

    async def fake_iter_bytes():
        yield full_bytes

    async def fake_aclose():
        return None

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "image/jpeg"}
    fake_response.aiter_bytes = fake_iter_bytes
    fake_response.aclose = fake_aclose

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        def build_request(self, method, url, headers=None):
            return (method, url, headers)

        async def send(self, req, stream=True):
            return fake_response

        async def aclose(self):
            return None

    monkeypatch.setattr(endpoints.httpx, "AsyncClient", FakeAsyncClient)

    client = TestClient(app)
    resp = client.get("/api/v1/drive/image/FULL_FILE_1?size=full&download=true")

    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == 'attachment; filename="273A7563.jpg"'
    assert "max-age=604800" in resp.headers["cache-control"]

import base64
from io import BytesIO
from unittest.mock import MagicMock, patch
import httpx
import numpy as np
import pytest
from celery.exceptions import Retry
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services import drive_service
from app.services.embedding_store import EmbeddingStore
from app.workers import tasks
from app.api import endpoints


class FakeFolderRedis:
    def __init__(self):
        self.strings = {}
        self.sets = {}

    async def set(self, key, value, ex=None):
        self.strings[key] = str(value)

    async def delete(self, *keys):
        for key in keys:
            self.strings.pop(key, None)
            self.sets.pop(key, None)

    async def aclose(self):
        return None

    def sadd(self, key, value):
        bucket = self.sets.setdefault(key, set())
        if value in bucket:
            return 0
        bucket.add(value)
        return 1

    def expire(self, key, ttl):
        return True

    def decr(self, key):
        current = int(self.strings.get(key, 0)) - 1
        self.strings[key] = str(current)
        return current

    def get(self, key):
        return self.strings.get(key)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test_embeddings.db")
    store = EmbeddingStore(db_path=db_path)
    monkeypatch.setattr(endpoints, "embedding_store", store)
    monkeypatch.setattr(tasks, "embedding_store", store)
    monkeypatch.setattr(endpoints.image_cache_service, "cache_dir", tmp_path / "thumbs")
    monkeypatch.setattr(tasks.image_cache_service, "cache_dir", tmp_path / "thumbs")
    monkeypatch.setattr(endpoints.settings, "PREWARM_THUMBNAILS_ON_SEARCH", False)
    return store


def _make_jpeg_bytes() -> bytes:
    image = Image.new("RGB", (32, 32), color=(120, 180, 220))
    buf = BytesIO()
    image.save(buf, format="JPEG")
    return buf.getvalue()


def test_extract_folder_id_handles_urls_fbclid_and_bare_id():
    url_with_fbclid = (
        "https://drive.google.com/drive/folders/1Mrnep4qIADsLTHyGvfldMZ-e0O5bakFM"
        "?fbclid=PAZXh0bgNhZW0CMTEAcGRvZg"
    )
    assert drive_service.extract_folder_id(url_with_fbclid) == "1Mrnep4qIADsLTHyGvfldMZ-e0O5bakFM"

    query_id_with_fbclid = (
        "https://drive.google.com/open?fbclid=FAKEID123&id=1Mrnep4qIADsLTHyGvfldMZ-e0O5bakFM"
    )
    assert drive_service.extract_folder_id(query_id_with_fbclid) == "1Mrnep4qIADsLTHyGvfldMZ-e0O5bakFM"

    assert drive_service.extract_folder_id("1Mrnep4qIADsLTHyGvfldMZ-e0O5bakFM") == "1Mrnep4qIADsLTHyGvfldMZ-e0O5bakFM"


def test_parse_public_embedded_folder_extracts_title_and_images():
    html = """<!DOCTYPE html><html><head><title>16.10.2026 - siqui - Google Drive</title></head><body>
    <div class="flip-entries">
      <div class="flip-entry" id="entry-FILE_IMG_1">
        <a href="https://drive.google.com/file/d/FILE_IMG_1/view">
          <div class="flip-entry-list-icon"><img src="https://drive-thirdparty.googleusercontent.com/16/type/image/jpeg"/></div>
          <div class="flip-entry-title">273A7563.jpg</div>
        </a>
      </div>
      <div class="flip-entry" id="entry-SUBFOLDER_1">
        <a href="https://drive.google.com/drive/folders/SUBFOLDER_1">
          <div class="flip-entry-list-icon"><img src="https://drive-thirdparty.googleusercontent.com/16/type/application/vnd.google-apps.folder"/></div>
          <div class="flip-entry-title">Nested Folder</div>
        </a>
      </div>
      <div class="flip-entry" id="entry-DOC_1">
        <a href="https://drive.google.com/file/d/DOC_1/view">
          <div class="flip-entry-list-icon"><img src="https://drive-thirdparty.googleusercontent.com/16/type/application/pdf"/></div>
          <div class="flip-entry-title">notes.pdf</div>
        </a>
      </div>
    </div></body></html>"""

    folder_name, files = drive_service.parse_public_embedded_folder(html)
    assert folder_name == "16.10.2026 - siqui"
    assert len(files) == 1
    assert files[0]["id"] == "FILE_IMG_1"
    assert files[0]["name"] == "273A7563.jpg"
    assert "FILE_IMG_1" in files[0]["webContentLink"]
    assert "FILE_IMG_1" in files[0]["thumbnailLink"]


def test_parse_public_embedded_folder_rejects_private_page():
    with pytest.raises(PermissionError):
        drive_service.parse_public_embedded_folder("<html><title>Sign in - Google Accounts</title></html>")


def test_index_folder_endpoint_supports_public_drive_without_token(isolated_store, monkeypatch):
    fake_redis = FakeFolderRedis()
    queued_calls = []

    monkeypatch.setattr(endpoints.redis, "from_url", lambda *args, **kwargs: fake_redis)
    monkeypatch.setattr(
        endpoints.index_drive_file,
        "delay",
        lambda **kwargs: queued_calls.append(kwargs),
    )

    sample_files = [
        {
            "id": "FILE_1",
            "name": "photo_1.jpg",
            "webContentLink": "https://drive.usercontent.google.com/download?id=FILE_1&export=download",
            "thumbnailLink": "https://drive.google.com/thumbnail?id=FILE_1&sz=w800",
        },
        {
            "id": "FILE_2",
            "name": "photo_2.jpg",
            "webContentLink": "https://drive.usercontent.google.com/download?id=FILE_2&export=download",
            "thumbnailLink": "https://drive.google.com/thumbnail?id=FILE_2&sz=w800",
        },
    ]

    with patch.object(endpoints, "list_public_drive_folder", return_value=("16.10.2026 - siqui", sample_files)):
        client = TestClient(app)
        response = client.post(
            "/api/v1/folders/index",
            json={
                "drive_link": "https://drive.google.com/drive/folders/1Mrnep4qIADsLTHyGvfldMZ-e0O5bakFM?fbclid=XYZ"
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["folder_id"] == "1Mrnep4qIADsLTHyGvfldMZ-e0O5bakFM"
    assert body["total_files"] == 2

    stored = isolated_store.get_folder("1Mrnep4qIADsLTHyGvfldMZ-e0O5bakFM")
    assert stored is not None
    assert stored["name"] == "16.10.2026 - siqui"
    assert stored["access_token"] is None
    assert stored["status"] == "indexing"
    assert len(queued_calls) == 2
    assert queued_calls[0]["access_token"] is None


def test_index_drive_file_downloads_public_file_and_deduplicates_counter(isolated_store, monkeypatch):
    fake_redis = FakeFolderRedis()
    fake_redis.strings["folder_remaining:folder-pub"] = "1"
    monkeypatch.setattr(tasks, "redis_text_client", fake_redis)

    isolated_store.create_or_update_folder(
        folder_id="folder-pub",
        name="Public Album",
        drive_folder_id="folder-pub",
        access_token=None,
        status="indexing",
        photo_count=1,
    )

    jpeg_bytes = _make_jpeg_bytes()
    encoding = np.ones(128, dtype=np.float64) * 0.25

    with patch.object(tasks, "download_file", return_value=jpeg_bytes) as mock_dl, \
         patch.object(tasks, "get_face_encodings", return_value=[encoding]):
        tasks.index_drive_file.run(
            folder_id="folder-pub",
            file_id="file-pub-1",
            file_name="img1.jpg",
            access_token=None,
            download_url="https://drive.usercontent.google.com/download?id=file-pub-1&export=download",
            thumbnail_url="https://drive.google.com/thumbnail?id=file-pub-1&sz=w800",
        )
        tasks.index_drive_file.run(
            folder_id="folder-pub",
            file_id="file-pub-1",
            file_name="img1.jpg",
            access_token=None,
            download_url="https://drive.usercontent.google.com/download?id=file-pub-1&export=download",
            thumbnail_url="https://drive.google.com/thumbnail?id=file-pub-1&sz=w800",
        )

    assert mock_dl.call_count == 2
    assert fake_redis.get("folder_remaining:folder-pub") == "0"
    folder = isolated_store.get_folder("folder-pub")
    assert folder["status"] == "ready"
    assert folder["faces_count"] == 1


def test_index_drive_file_retries_without_decrementing_counter_on_transient_error(isolated_store, monkeypatch):
    fake_redis = FakeFolderRedis()
    fake_redis.strings["folder_remaining:folder-retry"] = "1"
    monkeypatch.setattr(tasks, "redis_text_client", fake_redis)

    isolated_store.create_or_update_folder(
        folder_id="folder-retry",
        name="Retry Album",
        drive_folder_id="folder-retry",
        access_token=None,
        status="indexing",
        photo_count=1,
    )

    with patch.object(tasks, "download_file", side_effect=httpx.ConnectTimeout("timeout")), \
         patch.object(tasks.index_drive_file, "retry", side_effect=Retry()) as mock_retry:
        with pytest.raises(Retry):
            tasks.index_drive_file.run(
                folder_id="folder-retry",
                file_id="file-retry-1",
                file_name="retry.jpg",
                access_token=None,
            )

    assert mock_retry.called
    assert fake_redis.get("folder_remaining:folder-retry") == "1"
    assert isolated_store.get_folder("folder-retry")["status"] == "indexing"


def test_get_drive_image_streams_public_file_without_token(isolated_store, monkeypatch):
    isolated_store.create_or_update_folder(
        folder_id="folder-stream",
        name="Stream Album",
        drive_folder_id="folder-stream",
        access_token=None,
        status="ready",
        photo_count=1,
    )
    isolated_store.save_face_encodings(
        folder_id="folder-stream",
        file_id="FILE_PUBLIC_1",
        file_name="public.jpg",
        encodings=[np.ones(128, dtype=np.float64) * 0.1],
    )

    jpeg_bytes = _make_jpeg_bytes()

    async def fake_iter_bytes():
        yield jpeg_bytes

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "image/jpeg"}
    fake_response.aiter_bytes = fake_iter_bytes
    fake_response.aclose = MagicMock(return_value=None)

    async def fake_aclose():
        return None

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
    response = client.get("/api/v1/drive/image/FILE_PUBLIC_1")
    assert response.status_code == 200
    assert response.content == jpeg_bytes
    assert response.headers["content-type"].startswith("image/jpeg")


def test_search_folder_faces_endpoint_returns_matching_file(isolated_store, monkeypatch):
    isolated_store.create_or_update_folder(
        folder_id="folder-search",
        name="Search Album",
        drive_folder_id="folder-search",
        access_token=None,
        status="ready",
        photo_count=2,
    )
    isolated_store.save_face_encodings(
        folder_id="folder-search",
        file_id="FILE_MATCH",
        file_name="match.jpg",
        encodings=[np.ones(128, dtype=np.float64) * 0.4],
        download_url="https://drive.usercontent.google.com/download?id=FILE_MATCH&export=download",
        thumbnail_url="https://drive.google.com/thumbnail?id=FILE_MATCH&sz=w800",
    )
    isolated_store.save_face_encodings(
        folder_id="folder-search",
        file_id="FILE_OTHER",
        file_name="other.jpg",
        encodings=[np.ones(128, dtype=np.float64) * 0.9],
    )

    monkeypatch.setattr(
        endpoints,
        "get_face_encodings",
        lambda _bytes: [np.ones(128, dtype=np.float64) * 0.41],
    )

    b64_selfie = base64.b64encode(_make_jpeg_bytes()).decode("ascii")
    client = TestClient(app)
    response = client.post(
        "/api/v1/folders/folder-search/search",
        json={"target_face": b64_selfie, "tolerance": 0.6},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["folder_id"] == "folder-search"
    assert body["total_photos"] == 2
    assert len(body["matches"]) == 1
    assert body["matches"][0]["file_id"] == "FILE_MATCH"
    assert body["matches"][0]["confidence"] > 0.8

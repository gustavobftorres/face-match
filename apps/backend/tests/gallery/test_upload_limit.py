from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from app.api.gallery_limit import GalleryUploadLimit
from app.core.config import settings


def test_upload_limit_uses_configured_prefix_and_optional_slash(monkeypatch):
    monkeypatch.setattr(settings, 'API_V1_STR', '/custom/v2')
    app = FastAPI()
    app.add_middleware(GalleryUploadLimit)

    @app.post('/custom/v2/events/{event_id}/gallery/search')
    async def endpoint(request: Request, event_id: str):
        return {'size': len(await request.body()), 'id': event_id}

    client = TestClient(app)
    base = '/custom/v2/events/example/gallery/search'
    assert client.post(base, content=b'valid').json()['size'] == 5
    large = b'x' * (5 * 1024 * 1024 + 65537)
    assert client.post(base, content=large).status_code == 413
    assert client.post(base + '/', content=large).status_code == 413

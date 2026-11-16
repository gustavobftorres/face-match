"""Cap multipart upload bytes before Starlette's multipart parser buffers them."""
import re
from starlette.responses import PlainTextResponse
from app.core.config import settings


class GalleryUploadLimit:
    def __init__(self, app):
        self.app = app
        self.path = re.compile(re.escape(settings.API_V1_STR.rstrip('/')) + r'/events/[^/]+/gallery/search/?')

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST' or not self.path.fullmatch(scope['path']):
            return await self.app(scope, receive, send)
        limit = 5 * 1024 * 1024 + 65536
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            size += len(chunk)
            if size > limit:
                return await PlainTextResponse('Upload too large', status_code=413)(scope, receive, send)
            chunks.append(chunk)
            if not message.get('more_body', False):
                break
        body = b''.join(chunks)
        delivered = False
        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        await self.app(scope, replay, send)

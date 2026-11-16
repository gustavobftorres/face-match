"""Event-scoped gallery indexing; no legacy index or image cache is used."""
from io import BytesIO
from urllib.parse import urljoin, urlsplit
from uuid import UUID, uuid4

import httpx
import psycopg
import logging
import re
from PIL import Image, ImageOps
from psycopg.types.json import Jsonb
from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.session import tenant_session
from app.db.gallery_lock import lock_gallery
from app.services.drive_service import parse_public_embedded_folder

MAX_FILES = 30
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000


def download_image(file_id):
    url = settings.DRIVE_PUBLIC_DOWNLOAD_URL.format(file_id=file_id)
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        for _ in range(5):
            parsed = urlsplit(url)
            host = (parsed.hostname or '').lower()
            if parsed.scheme != 'https' or parsed.username or parsed.password or not any(host == suffix or host.endswith('.' + suffix) for suffix in ('google.com', 'googleusercontent.com', 'gstatic.com')):
                raise ValueError('Untrusted download host')
            with client.stream('GET', url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location'])
                    continue
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_IMAGE_BYTES:
                        raise ValueError('Image too large')
                return bytes(content)
    raise ValueError('Too many redirects')


def process_image(data):
    from app.services.ai_service import get_face_encodings
    with Image.open(BytesIO(data)) as image:
        if image.width * image.height > MAX_PIXELS:
            raise ValueError('Image dimensions too large')
        image = ImageOps.exif_transpose(image).convert('RGB')
        output = BytesIO()
        image.save(output, format='JPEG', quality=88)
    normalized = output.getvalue()
    if len(normalized) > MAX_IMAGE_BYTES:
        raise ValueError('Image too large')
    vectors = [vector.tolist() for vector in get_face_encodings(normalized)]
    return normalized, vectors


def list_gallery_folder(folder_id):
    # Avoid the legacy listing's unbounded response and shortcut resolution.
    url = settings.DRIVE_EMBEDDED_FOLDER_URL.format(folder_id=folder_id)
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        with client.stream('GET', url) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > 2 * 1024 * 1024:
                    raise ValueError('Folder listing too large')
    html = content.decode('utf-8')
    if len(re.findall(r'class="flip-entry"', html)) > MAX_FILES or 'application/vnd.google-apps.shortcut' in html:
        raise ValueError('Folder exceeds limit or contains shortcuts')
    return parse_public_embedded_folder(html)


def valid_job(conn, tid, eid, jid, lease):
    return conn.execute('''SELECT j.folder_id FROM gallery_jobs j JOIN events e ON e.tenant_id = j.tenant_id AND e.id = j.event_id
        JOIN tenants t ON t.id = j.tenant_id WHERE j.id = %s AND j.tenant_id = %s AND j.event_id = %s
        AND j.status = 'processing' AND j.lease_token = %s AND j.lease_until > now() AND t.status = 'active'
        AND EXISTS (SELECT 1 FROM tenant_memberships m WHERE m.tenant_id = j.tenant_id AND m.user_id = j.requested_by AND m.role IN ('owner','admin')) FOR UPDATE OF j''', (jid, tid, eid, lease)).fetchone()


@celery_app.task(name='gallery.recover_pending')
def recover_pending():
    if not settings.GALLERY_DISPATCHER_DATABASE_URL:
        raise RuntimeError('GALLERY_DISPATCHER_DATABASE_URL is required for gallery recovery')
    with psycopg.connect(settings.GALLERY_DISPATCHER_DATABASE_URL) as conn:
        rows = conn.execute('SELECT * FROM public.gallery_pending_jobs()').fetchall()
    for tid, eid, jid in rows:
        try:
            index_event.delay(str(tid), str(eid), str(jid))
        except Exception:
            logging.exception('Could not enqueue gallery job')


@celery_app.task(name='gallery.index_event')
def index_event(tenant_id, event_id, job_id):
    tid, eid, jid, lease = UUID(tenant_id), UUID(event_id), UUID(job_id), uuid4()
    with tenant_session(settings.DATABASE_URL, tid) as conn:
        row = conn.execute('''SELECT j.status, j.lease_until < now(), t.status = 'active',
            EXISTS (SELECT 1 FROM tenant_memberships m WHERE m.tenant_id=j.tenant_id AND m.user_id=j.requested_by AND m.role IN ('owner','admin'))
            FROM gallery_jobs j JOIN tenants t ON t.id=j.tenant_id WHERE j.id=%s AND j.tenant_id=%s AND j.event_id=%s FOR UPDATE OF j''', (jid, tid, eid)).fetchone()
        if not row or not (row[0] == 'queued' or (row[0] == 'processing' and row[1])):
            return
        if not row[2] or not row[3]:
            conn.execute("UPDATE gallery_jobs SET status='failed', lease_token=NULL, lease_until=NULL WHERE id=%s", (jid,))
            return
        conn.execute("UPDATE gallery_jobs SET status='processing', lease_token=%s, lease_until=now()+interval '10 minutes' WHERE id=%s", (lease, jid))
    try:
        with tenant_session(settings.DATABASE_URL, tid) as conn:
            row = valid_job(conn, tid, eid, jid, lease)
            if not row:
                return
        _, files = list_gallery_folder(row[0])
        if len(files) > MAX_FILES:
            raise ValueError('Folder exceeds file limit')
        processed = []
        for file in files:
            data, vectors = process_image(download_image(file['id']))
            processed.append((uuid4(), file['id'], data, vectors))
        with tenant_session(settings.DATABASE_URL, tid) as conn:
            lock_gallery(conn, eid)
            if not valid_job(conn, tid, eid, jid, lease):
                conn.execute("UPDATE gallery_jobs SET status='failed', lease_token=NULL, lease_until=NULL WHERE id=%s AND tenant_id=%s AND event_id=%s AND status='processing' AND lease_token=%s", (jid, tid, eid, lease))
                return
            conn.execute('DELETE FROM gallery_photos WHERE tenant_id=%s AND event_id=%s', (tid, eid))
            for photo_id, source_id, data, vectors in processed:
                conn.execute('INSERT INTO gallery_photos (id,tenant_id,event_id,source_id,image_bytes,embeddings) VALUES (%s,%s,%s,%s,%s,%s)', (photo_id, tid, eid, source_id, data, Jsonb(vectors)))
            conn.execute("UPDATE gallery_jobs SET status='ready', lease_token=NULL, lease_until=NULL WHERE id=%s AND lease_token=%s", (jid, lease))
    except Exception:
        with tenant_session(settings.DATABASE_URL, tid) as conn:
            conn.execute("UPDATE gallery_jobs SET status='failed', lease_token=NULL, lease_until=NULL WHERE id=%s AND tenant_id=%s AND event_id=%s AND status='processing' AND lease_token=%s", (jid, tid, eid, lease))
        raise

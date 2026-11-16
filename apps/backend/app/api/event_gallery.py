"""New event gallery routes; independent of the legacy public Drive index."""
import hmac
from uuid import UUID, uuid4
from io import BytesIO
from PIL import Image, UnidentifiedImageError

import psycopg
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from app.api.app_session import authenticated, check_origin, digest
from app.core.config import settings
from app.db.session import tenant_session
from app.db.gallery_lock import lock_gallery
from app.services.drive_service import extract_folder_id
from app.workers.gallery_tasks import index_event

router = APIRouter()


def require_csrf(request, auth):
    check_origin(request)
    value = request.headers.get('x-csrf-token', '')
    if not value or len(value) > 128 or not hmac.compare_digest(digest(value), auth[2]):
        raise HTTPException(403, 'Invalid CSRF token')


def allowed(conn, eid, uid, admin_only=False):
    return bool(conn.execute('''SELECT 1 FROM events e WHERE e.id = %s AND (
        EXISTS (SELECT 1 FROM tenant_memberships m WHERE m.tenant_id = e.tenant_id AND m.user_id = %s AND m.role IN ('owner','admin'))
        OR (%s AND e.status = 'published' AND EXISTS (SELECT 1 FROM event_participations p
            WHERE p.tenant_id = e.tenant_id AND p.event_id = e.id AND p.user_id = %s)))''',
        (eid, uid, not admin_only, uid)).fetchone())


class IndexRequest(BaseModel):
    folder: str


@router.post('/events/{event_id}/gallery/index', status_code=202)
def start_index(event_id: UUID, body: IndexRequest, request: Request, auth=Depends(authenticated)):
    require_csrf(request, auth)
    tid, uid = auth[:2]
    try:
        folder_id = extract_folder_id(body.folder)
    except ValueError:
        raise HTTPException(422, 'Invalid Drive folder')
    job = uuid4()
    try:
        with tenant_session(settings.DATABASE_URL, tid) as conn:
            if not allowed(conn, event_id, uid, True):
                raise HTTPException(404, 'Not found')
            conn.execute("INSERT INTO gallery_jobs (id,tenant_id,event_id,requested_by,folder_id,status) VALUES (%s,%s,%s,%s,%s,'queued')", (job, tid, event_id, uid, folder_id))
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, 'Indexing already in progress')
    try:
        index_event.delay(str(tid), str(event_id), str(job))
    except Exception:
        # The persisted queued row is an outbox; Celery beat retries delivery.
        pass
    return {'id': str(job), 'status': 'queued'}


@router.get('/events/{event_id}/gallery/jobs/latest')
def latest_job(event_id: UUID, response: Response, auth=Depends(authenticated)):
    with tenant_session(settings.DATABASE_URL, auth[0]) as conn:
        if not allowed(conn, event_id, auth[1], True):
            raise HTTPException(404, 'Not found')
        row = conn.execute('SELECT id, status FROM gallery_jobs WHERE event_id = %s ORDER BY created_at DESC, id DESC LIMIT 1', (event_id,)).fetchone()
    response.headers['Cache-Control'] = 'private, no-store'
    return {'job': {'id': str(row[0]), 'status': row[1]} if row else None}


@router.get('/events/{event_id}/gallery/jobs/{job_id}')
def job_status(event_id: UUID, job_id: UUID, response: Response, auth=Depends(authenticated)):
    with tenant_session(settings.DATABASE_URL, auth[0]) as conn:
        if not allowed(conn, event_id, auth[1], True):
            raise HTTPException(404, 'Not found')
        row = conn.execute('SELECT status FROM gallery_jobs WHERE id = %s AND event_id = %s', (job_id, event_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Not found')
    response.headers['Cache-Control'] = 'private, no-store'
    return {'id': str(job_id), 'status': row[0]}


def extract_selfie(data):
    from app.services.ai_service import get_face_encodings
    return get_face_encodings(data)


@router.post('/events/{event_id}/gallery/search')
def search(event_id: UUID, request: Request, response: Response, selfie: UploadFile = File(...), auth=Depends(authenticated)):
    require_csrf(request, auth)
    tid, uid = auth[:2]
    with tenant_session(settings.DATABASE_URL, tid) as conn:
        if not allowed(conn, event_id, uid):
            raise HTTPException(404, 'Not found')
    data = selfie.file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, 'Image too large')
    try:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > 20_000_000 or max(image.width, image.height) > 10000:
                raise HTTPException(413, 'Image dimensions too large')
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, 'Invalid image')
    encodings = extract_selfie(data)
    if len(encodings) != 1:
        raise HTTPException(422, 'Provide a photo with exactly one face')
    import numpy as np
    vector = np.asarray(encodings[0], dtype=float)
    search_id = uuid4()
    with tenant_session(settings.DATABASE_URL, tid) as conn:
        lock_gallery(conn, event_id)
        if not allowed(conn, event_id, uid):
            raise HTTPException(404, 'Not found')
        photos = conn.execute('SELECT id, embeddings FROM gallery_photos WHERE event_id = %s', (event_id,)).fetchall()
        matches = [pid for pid, vectors in photos if any(np.linalg.norm(np.asarray(v) - vector) < 0.6 for v in vectors)]
        conn.execute('INSERT INTO gallery_searches (id,tenant_id,event_id,user_id) VALUES (%s,%s,%s,%s)', (search_id, tid, event_id, uid))
        for pid in matches:
            conn.execute('INSERT INTO gallery_results VALUES (%s,%s,%s,%s)', (tid, event_id, search_id, pid))
    response.headers['Cache-Control'] = 'private, no-store'
    return {'id': str(search_id), 'photos': [str(pid) for pid in matches]}


@router.get('/events/{event_id}/gallery/searches/{search_id}/photos/{photo_id}')
def get_photo(event_id: UUID, search_id: UUID, photo_id: UUID, auth=Depends(authenticated)):
    tid, uid = auth[:2]
    with tenant_session(settings.DATABASE_URL, tid) as conn:
        if not allowed(conn, event_id, uid):
            raise HTTPException(404, 'Not found')
        row = conn.execute('''SELECT p.image_bytes FROM gallery_results r
            JOIN gallery_searches s ON (s.tenant_id,s.event_id,s.id) = (r.tenant_id,r.event_id,r.search_id)
            JOIN gallery_photos p ON (p.tenant_id,p.event_id,p.id) = (r.tenant_id,r.event_id,r.photo_id)
            WHERE r.event_id = %s AND r.search_id = %s AND r.photo_id = %s AND s.user_id = %s''', (event_id, search_id, photo_id, uid)).fetchone()
    if not row:
        raise HTTPException(404, 'Not found')
    return Response(bytes(row[0]), media_type='image/jpeg', headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'})

"""Organizer administration of events and branding; independent of legacy admin routes.

The tenant always comes from the validated Host (via the session), never from the
client. Every request runs in a per-transaction RLS context with the runtime role
and requires an owner/admin membership; mutations also require Origin and CSRF.
"""
import re
import unicodedata
from contextlib import contextmanager
from typing import Optional
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.app_session import authenticated
from app.api.event_gallery import require_csrf
from app.api.tenant_context import tenant_id_for_host
from app.core.config import settings
from app.db.session import tenant_session
from app.services.branding import MAX_LOGO_UPLOAD_BYTES, PALETTES, InvalidLogo, logo_token, process_logo



class SafeValidationRoute(APIRoute):
    """422 bodies omit the rejected input: echoing it would 500 on values such as lone surrogates."""
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                detail = [{'loc': list(item.get('loc', ())), 'msg': str(item.get('msg', '')), 'type': item.get('type', '')} for item in error.errors()]
                return JSONResponse({'detail': detail}, status_code=422)
        return safe


router = APIRouter(prefix='/admin', route_class=SafeValidationRoute)
SLUG = r'^[a-z0-9]+(-[a-z0-9]+)*$'
EVENT_COLUMNS = 'id, name, slug, status, description, created_at, updated_at'
EVENT_KEYS = ('id', 'name', 'slug', 'status', 'description', 'created_at', 'updated_at')
NO_STORE = {'Cache-Control': 'private, no-store'}


@contextmanager
def admin_session(auth):
    """Tenant transaction in which the session user is verified as owner/admin."""
    tid, uid = auth[:2]
    with tenant_session(settings.DATABASE_URL, tid) as conn:
        role = conn.execute("SELECT role FROM tenant_memberships WHERE tenant_id = %s AND user_id = %s AND role IN ('owner','admin')", (tid, uid)).fetchone()
        if not role:
            raise HTTPException(403, 'Administrator access required')
        yield conn, tid, role[0]


def event_json(row):
    data = dict(zip(EVENT_KEYS, row))
    data['id'] = str(data['id'])
    data['created_at'], data['updated_at'] = data['created_at'].isoformat(), data['updated_at'].isoformat()
    return data


def clean_text(value, *, multiline=False):
    """Strip, then reject NUL and other control characters (newlines/tabs only in descriptions)."""
    if value is None:
        return None
    value = value.strip()
    allowed = '\n\t' if multiline else ''
    if any(unicodedata.category(c) == 'Cs' or (unicodedata.category(c) == 'Cc' and c not in allowed) for c in value):
        raise ValueError('control or invalid characters are not allowed')
    if not any(unicodedata.category(c)[0] not in 'CZ' for c in value):
        return ''  # nothing visible (empty, whitespace or format characters only)
    return value


class EventFields(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_validator('name', check_fields=False)
    @classmethod
    def _name(cls, value):
        value = clean_text(value)
        if value is not None and not value:
            raise ValueError('name must not be blank')
        return value

    @field_validator('description', check_fields=False)
    @classmethod
    def _description(cls, value):
        return clean_text(value, multiline=True) or None


class EventCreate(EventFields):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=63, pattern=SLUG)
    description: Optional[str] = Field(default=None, max_length=2000)


class EventUpdate(EventFields):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=63, pattern=SLUG)
    description: Optional[str] = Field(default=None, max_length=2000)


@router.get('/access')
def access(response: Response, auth=Depends(authenticated)):
    with admin_session(auth) as (_, _tid, role):
        pass
    response.headers.update(NO_STORE)
    return {'role': role}


@router.get('/events')
def list_events(response: Response, auth=Depends(authenticated)):
    with admin_session(auth) as (conn, _tid, _role):
        rows = conn.execute(f'SELECT {EVENT_COLUMNS} FROM events ORDER BY created_at DESC, id DESC').fetchall()
    response.headers.update(NO_STORE)
    return {'events': [event_json(row) for row in rows]}


@router.get('/events/{event_id}')
def get_event(event_id: UUID, response: Response, auth=Depends(authenticated)):
    with admin_session(auth) as (conn, _tid, _role):
        row = conn.execute(f'SELECT {EVENT_COLUMNS} FROM events WHERE id = %s', (event_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Not found')
    response.headers.update(NO_STORE)
    return event_json(row)


@router.post('/events', status_code=201)
def create_event(body: EventCreate, request: Request, response: Response, auth=Depends(authenticated)):
    require_csrf(request, auth)
    try:
        with admin_session(auth) as (conn, tid, _role):
            row = conn.execute(f'INSERT INTO events (id, tenant_id, name, slug, description) VALUES (%s, %s, %s, %s, %s) RETURNING {EVENT_COLUMNS}',
                               (uuid4(), tid, body.name, body.slug, body.description)).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, 'Event slug already in use')
    response.headers.update(NO_STORE)
    return event_json(row)


@router.patch('/events/{event_id}')
def update_event(event_id: UUID, body: EventUpdate, request: Request, response: Response, auth=Depends(authenticated)):
    require_csrf(request, auth)
    changes = body.model_dump(exclude_unset=True)
    if not changes or ('name' in changes and changes['name'] is None) or ('slug' in changes and changes['slug'] is None):
        raise HTTPException(422, 'Nothing to update')
    assignments = ', '.join(f'{column} = %s' for column in changes)  # column names come from the model, never the client
    try:
        with admin_session(auth) as (conn, _tid, _role):
            row = conn.execute(f'UPDATE events SET {assignments}, updated_at = now() WHERE id = %s RETURNING {EVENT_COLUMNS}',
                               (*changes.values(), event_id)).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, 'Event slug already in use')
    if not row:
        raise HTTPException(404, 'Not found')
    response.headers.update(NO_STORE)
    return event_json(row)


def transition(event_id: UUID, target: str, allowed_from: tuple, request: Request, response: Response, auth):
    require_csrf(request, auth)
    with admin_session(auth) as (conn, _tid, _role):
        row = conn.execute(f'UPDATE events SET status = %s, updated_at = now() WHERE id = %s AND status = ANY(%s) RETURNING {EVENT_COLUMNS}',
                           (target, event_id, list(allowed_from))).fetchone()
        if not row and not conn.execute('SELECT 1 FROM events WHERE id = %s', (event_id,)).fetchone():
            raise HTTPException(404, 'Not found')
    if not row:
        raise HTTPException(409, f'Event cannot move to {target} from its current status')
    response.headers.update(NO_STORE)
    return event_json(row)


@router.post('/events/{event_id}/publish')
def publish_event(event_id: UUID, request: Request, response: Response, auth=Depends(authenticated)):
    return transition(event_id, 'published', ('draft', 'closed'), request, response, auth)


@router.post('/events/{event_id}/unpublish')
def unpublish_event(event_id: UUID, request: Request, response: Response, auth=Depends(authenticated)):
    return transition(event_id, 'draft', ('published',), request, response, auth)


@router.post('/events/{event_id}/close')
def close_event(event_id: UUID, request: Request, response: Response, auth=Depends(authenticated)):
    return transition(event_id, 'closed', ('draft', 'published'), request, response, auth)


def logo_url(tid, version: int) -> str:
    return f'/api/v1/tenant/logo/{logo_token(tid, version)}.png'


def branding_json(row, tid):
    palette, colors, has_logo, version = row
    return {'palette': palette, 'colors': colors or {}, 'logo_url': logo_url(tid, version) if has_logo else None, 'theme_version': version,
            'palettes': {key: value for key, value in PALETTES.items()}}


def read_branding(conn, tid):
    row = conn.execute('SELECT palette, colors, logo_png IS NOT NULL, theme_version FROM tenant_branding WHERE tenant_id = %s', (tid,)).fetchone()
    return row or (None, {}, False, 1)


class BrandingUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    palette: str = Field(min_length=1, max_length=32)


@router.get('/branding')
def get_branding(response: Response, auth=Depends(authenticated)):
    with admin_session(auth) as (conn, tid, _role):
        row = read_branding(conn, tid)
    response.headers.update(NO_STORE)
    return branding_json(row, tid)


@router.put('/branding')
def update_branding(body: BrandingUpdate, request: Request, response: Response, auth=Depends(authenticated)):
    require_csrf(request, auth)
    colors = PALETTES.get(body.palette)
    if colors is None:
        raise HTTPException(422, 'Unknown palette')
    with admin_session(auth) as (conn, tid, _role):
        conn.execute('''INSERT INTO tenant_branding (tenant_id, palette, colors) VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (tenant_id) DO UPDATE SET palette = EXCLUDED.palette, colors = EXCLUDED.colors,
            theme_version = tenant_branding.theme_version + 1''', (tid, body.palette, Jsonb(colors)))
        row = read_branding(conn, tid)
    response.headers.update(NO_STORE)
    return branding_json(row, tid)


@router.put('/branding/logo')
def upload_logo(request: Request, response: Response, logo: UploadFile = File(...), auth=Depends(authenticated)):
    require_csrf(request, auth)
    with admin_session(auth):
        pass  # authorize before spending CPU on decoding
    data = logo.file.read(MAX_LOGO_UPLOAD_BYTES + 1)
    try:
        png = process_logo(data)
    except InvalidLogo as error:
        raise HTTPException(error.status, str(error))
    with admin_session(auth) as (conn, tid, _role):
        conn.execute('''INSERT INTO tenant_branding (tenant_id, logo_png) VALUES (%s, %s)
            ON CONFLICT (tenant_id) DO UPDATE SET logo_png = EXCLUDED.logo_png, theme_version = tenant_branding.theme_version + 1''', (tid, png))
        row = read_branding(conn, tid)
    response.headers.update(NO_STORE)
    return branding_json(row, tid)


@router.delete('/branding/logo')
def delete_logo(request: Request, response: Response, auth=Depends(authenticated)):
    require_csrf(request, auth)
    with admin_session(auth) as (conn, tid, _role):
        conn.execute('UPDATE tenant_branding SET logo_png = NULL, theme_version = theme_version + 1 WHERE tenant_id = %s AND logo_png IS NOT NULL', (tid,))
        row = read_branding(conn, tid)
    response.headers.update(NO_STORE)
    return branding_json(row, tid)


public_router = APIRouter()


@public_router.get('/tenant/logo/{token}.png')
def public_logo(token: str, request: Request, tid: UUID = Depends(tenant_id_for_host)):
    """Public logo; tenant from the hostname only. The path holds an opaque tenant+version
    token, so only the exact current URL is cacheable as immutable."""
    miss = HTTPException(404, 'Not found', headers={'Cache-Control': 'no-store'})
    if not re.fullmatch(r'[0-9a-f]{32}', token):
        raise miss
    with tenant_session(settings.DATABASE_URL, tid) as conn:
        row = conn.execute("""SELECT b.theme_version FROM tenant_branding b JOIN tenants t ON t.id = b.tenant_id
            WHERE b.tenant_id = %s AND t.status = 'active' AND b.logo_png IS NOT NULL""", (tid,)).fetchone()
        if not row or token != logo_token(tid, row[0]):
            raise miss
        etag = f'"{token}"'
        headers = {'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; sandbox",
                   'Cache-Control': 'public, max-age=31536000, immutable', 'ETag': etag, 'Vary': 'Host'}
        if etag in [v.strip().removeprefix('W/') for v in request.headers.get('if-none-match', '').split(',')]:
            return Response(status_code=304, headers=headers)
        data = conn.execute('SELECT logo_png FROM tenant_branding WHERE tenant_id = %s', (tid,)).fetchone()[0]
    return Response(bytes(data), media_type='image/png', headers={**headers, 'Content-Disposition': 'inline; filename="logo.png"'})

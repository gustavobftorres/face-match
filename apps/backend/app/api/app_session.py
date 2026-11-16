"""Host-bound application sessions and event access, independent of legacy OAuth."""
import hashlib
import hmac
import secrets
from uuid import UUID, uuid4

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from google.auth.transport import requests as google_requests
from google.auth.exceptions import GoogleAuthError
from google.oauth2 import id_token
from pydantic import BaseModel

from app.api.tenant_context import canonical_host
from app.core.config import settings
from app.db.session import tenant_session

router = APIRouter()
SESSION = '__Host-fm_session'
CHALLENGE = '__Host-fm_login'
CSRF = '__Host-fm_csrf'


def digest(value: str) -> bytes:
    return hashlib.sha256(value.encode('utf-8')).digest()


def tenant_id(host: str = Depends(canonical_host)) -> UUID:
    with psycopg.connect(settings.DATABASE_URL) as conn:
        row = conn.execute('SELECT public.lookup_tenant_hostname(%s)', (host,)).fetchone()
    if not row or not row[0]:
        raise HTTPException(404, 'Not found')
    with tenant_session(settings.DATABASE_URL, row[0]) as conn:
        active = conn.execute("SELECT 1 FROM tenants WHERE id = %s AND status = 'active'", (row[0],)).fetchone()
    if not active:
        raise HTTPException(404, 'Not found')
    return row[0]


def check_origin(request: Request):
    # The Host has already been validated by tenant_id. Accept no forwarded headers.
    hosts = request.headers.getlist('host')
    origins = request.headers.getlist('origin')
    if len(hosts) != 1 or len(origins) != 1 or origins[0].lower() != 'https://' + hosts[0].lower():
        raise HTTPException(403, 'Invalid origin')


def verify_google_token(token: str):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(503, 'Login unavailable')
    try:
        claims = id_token.verify_oauth2_token(token, google_requests.Request(), settings.GOOGLE_CLIENT_ID)
    except (ValueError, GoogleAuthError):
        raise HTTPException(401, 'Invalid identity token')
    if claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com') or not claims.get('sub'):
        raise HTTPException(401, 'Invalid identity token')
    return claims


def set_cookie(response: Response, key: str, value: str, max_age: int, httponly: bool = True):
    response.set_cookie(key, value, max_age=max_age, secure=True, httponly=httponly, samesite='strict', path='/')


@router.post('/session/challenge')
def challenge(request: Request, response: Response, tid: UUID = Depends(tenant_id), host: str = Depends(canonical_host)):
    check_origin(request)
    nonce = secrets.token_urlsafe(32)
    with tenant_session(settings.DATABASE_URL, tid) as conn:
        conn.execute("INSERT INTO login_challenges (tenant_id, hostname, nonce_hash, expires_at) VALUES (%s, %s, %s, now() + interval '5 minutes')", (tid, host, digest(nonce)))
    set_cookie(response, CHALLENGE, nonce, 300)
    response.headers['Cache-Control'] = 'no-store'
    return {'nonce': nonce}


def get_google_verifier():
    return verify_google_token


class LoginBody(BaseModel):
    id_token: str


@router.post('/session/google')
def login(body: LoginBody, request: Request, response: Response, tid: UUID = Depends(tenant_id), host: str = Depends(canonical_host), verifier=Depends(get_google_verifier)):
    check_origin(request)
    nonce = request.cookies.get(CHALLENGE, '')
    if not nonce or len(nonce) > 128:
        raise HTTPException(401, 'Invalid login challenge')
    claims = verifier(body.id_token)
    if not isinstance(claims.get('nonce'), str) or not hmac.compare_digest(claims['nonce'], nonce):
        raise HTTPException(401, 'Invalid login challenge')
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with tenant_session(settings.DATABASE_URL, tid) as conn:
        consumed = conn.execute('DELETE FROM login_challenges WHERE nonce_hash = %s AND hostname = %s AND expires_at > now() RETURNING nonce_hash', (digest(nonce), host)).fetchone()
        if not consumed:
            raise HTTPException(401, 'Invalid login challenge')
        user = conn.execute('''INSERT INTO users (id, google_subject, email, display_name)
            VALUES (%s, %s, %s, %s) ON CONFLICT (google_subject) DO UPDATE
            SET email = EXCLUDED.email, display_name = EXCLUDED.display_name RETURNING id''',
            (uuid4(), claims['sub'], claims.get('email') if claims.get('email_verified') is True else None, claims.get('name'))).fetchone()[0]
        conn.execute("INSERT INTO app_sessions (token_hash, tenant_id, hostname, user_id, csrf_hash, expires_at) VALUES (%s, %s, %s, %s, %s, now() + interval '8 hours')", (digest(token), tid, host, user, digest(csrf)))
    set_cookie(response, SESSION, token, 28800)
    set_cookie(response, CSRF, csrf, 28800, httponly=False)
    response.delete_cookie(CHALLENGE, path='/', secure=True, httponly=True, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'
    return {'authenticated': True}


def authenticated(request: Request, tid: UUID = Depends(tenant_id), host: str = Depends(canonical_host)):
    token = request.cookies.get(SESSION, '')
    if not token or len(token) > 128:
        raise HTTPException(401, 'Authentication required')
    with tenant_session(settings.DATABASE_URL, tid) as conn:
        row = conn.execute('SELECT user_id, csrf_hash FROM app_sessions WHERE token_hash = %s AND hostname = %s AND expires_at > now() AND revoked_at IS NULL', (digest(token), host)).fetchone()
    if not row:
        raise HTTPException(401, 'Authentication required')
    return tid, row[0], row[1], token


@router.get('/session')
def current_session(response: Response, auth=Depends(authenticated)):
    response.headers['Cache-Control'] = 'no-store'
    return {'authenticated': True, 'user_id': str(auth[1])}


@router.delete('/session', status_code=204)
def logout(request: Request, response: Response, auth=Depends(authenticated)):
    check_origin(request)
    csrf = request.headers.get('x-csrf-token', '')
    if len(csrf) > 128 or not csrf or not hmac.compare_digest(digest(csrf), auth[2]):
        raise HTTPException(403, 'Invalid CSRF token')
    with tenant_session(settings.DATABASE_URL, auth[0]) as conn:
        conn.execute('UPDATE app_sessions SET revoked_at = now() WHERE token_hash = %s', (digest(auth[3]),))
    response.delete_cookie(SESSION, path='/', secure=True, httponly=True, samesite='strict')
    response.delete_cookie(CSRF, path='/', secure=True, samesite='strict')
    response.headers['Cache-Control'] = 'no-store'


@router.get('/events/{event_id}')
def get_event(event_id: UUID, response: Response, auth=Depends(authenticated)):
    tid, user_id, _, _ = auth
    with tenant_session(settings.DATABASE_URL, tid) as conn:
        row = conn.execute('''SELECT e.id, e.name, e.slug, e.status FROM events e
            WHERE e.id = %s AND (EXISTS (SELECT 1 FROM tenant_memberships m WHERE m.tenant_id = e.tenant_id AND m.user_id = %s AND m.role IN ('owner','admin'))
              OR (e.status = 'published' AND EXISTS (SELECT 1 FROM event_participations p WHERE p.tenant_id = e.tenant_id AND p.event_id = e.id AND p.user_id = %s)))''', (event_id, user_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, 'Not found')
    response.headers['Cache-Control'] = 'no-store'
    return dict(zip(('id', 'name', 'slug', 'status'), row))

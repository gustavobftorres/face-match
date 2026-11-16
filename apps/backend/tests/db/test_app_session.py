import os
from uuid import uuid4
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.app_session import router, get_google_verifier
from app.core.config import settings
from app.db.migrate import migrate
from app.db.provision_context import provision

ADMIN = os.getenv('TEST_DATABASE_ADMIN_URL')
RUNTIME = os.getenv('TEST_DATABASE_RUNTIME_URL')
pytestmark = pytest.mark.skipif(not ADMIN or not RUNTIME, reason='disposable PostgreSQL URLs not configured')

def test_sessions_and_event_authorization(monkeypatch):
    migrate(ADMIN)
    with psycopg.connect(RUNTIME) as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
    provision(ADMIN, role)
    monkeypatch.setattr(settings, 'DATABASE_URL', RUNTIME)
    a, b, event_a, draft_a, event_b = (uuid4() for _ in range(5))
    suffix = uuid4().hex
    host_a, host_b, host_alias = f'a-{suffix}.test', f'b-{suffix}.test', f'alias-{suffix}.test'
    with psycopg.connect(ADMIN) as conn:
        for tid, host in ((a, host_a), (b, host_b)):
            conn.execute("INSERT INTO tenants (id, name, slug) VALUES (%s, 'tenant', %s)", (tid, str(tid)))
            conn.execute('INSERT INTO tenant_domains (id, tenant_id, hostname) VALUES (%s, %s, %s)', (uuid4(), tid, host))
        conn.execute('INSERT INTO tenant_domains (id, tenant_id, hostname) VALUES (%s, %s, %s)', (uuid4(), a, host_alias))
        for eid, tid, status in ((event_a, a, 'published'), (draft_a, a, 'draft'), (event_b, b, 'published')):
            conn.execute('INSERT INTO events (id, tenant_id, name, slug, status) VALUES (%s, %s, %s, %s, %s)', (eid, tid, str(eid), str(eid), status))
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    state = {}
    app.dependency_overrides[get_google_verifier] = lambda: lambda token: {'sub': token, 'nonce': state['nonce'], 'email': 'unverified@example.com', 'email_verified': False}
    def client(host):
        return TestClient(app, base_url=f'https://{host}', headers={'origin': f'https://{host}'})
    def login(c, subject):
        state['nonce'] = c.post('/api/v1/session/challenge').json()['nonce']
        res = c.post('/api/v1/session/google', json={'id_token': subject})
        assert res.status_code == 200
        assert 'HttpOnly' in res.headers.get_list('set-cookie')[0] and 'Secure' in res.headers.get_list('set-cookie')[0]
    participant, admin, outsider, other_tenant = client(host_a), client(host_a), client(host_a), client(host_b)
    subject, admin_subject, outsider_subject = str(uuid4()), str(uuid4()), str(uuid4())
    challenge_nonce = participant.post('/api/v1/session/challenge').json()['nonce']
    state['nonce'] = challenge_nonce
    alias_client = client(host_alias)
    alias_client.cookies.set('__Host-fm_login', challenge_nonce, domain=host_alias, path='/')
    assert alias_client.post('/api/v1/session/google', json={'id_token': subject}).status_code == 401
    assert participant.post('/api/v1/session/google', json={'id_token': subject}).status_code == 200
    old_session = participant.cookies.get('__Host-fm_session')
    alias_client.cookies.set('__Host-fm_session', old_session, domain=host_alias, path='/')
    assert alias_client.get('/api/v1/session').status_code == 401
    old_challenge = state['nonce']
    replay = client(host_a)
    replay.cookies.set('__Host-fm_login', old_challenge, domain=host_a, path='/')
    assert replay.post('/api/v1/session/google', json={'id_token': subject}).status_code == 401
    login(admin, admin_subject)
    login(outsider, outsider_subject)
    login(other_tenant, subject)
    with psycopg.connect(ADMIN) as conn:
        rows = conn.execute('SELECT id, google_subject, email FROM users WHERE google_subject IN (%s, %s, %s)', (subject, admin_subject, outsider_subject)).fetchall()
        users = {s: uid for uid, s, email in rows if email is None}
        assert len(users) == 3
        conn.execute('INSERT INTO event_participations (tenant_id, event_id, user_id) VALUES (%s, %s, %s)', (a, event_a, users[subject]))
        conn.execute("INSERT INTO tenant_memberships VALUES (%s, %s, 'admin')", (a, users[admin_subject]))
    path = '/api/v1/events/'
    assert participant.get(path + str(event_a)).status_code == 200
    assert participant.get(path + str(draft_a)).status_code == 404
    assert participant.get(path + str(event_b)).status_code == 404
    assert admin.get(path + str(draft_a)).status_code == 200
    assert outsider.get(path + str(event_a)).status_code == 404
    assert other_tenant.get(path + str(event_a)).status_code == 404
    assert other_tenant.get(path + str(event_b)).status_code == 404
    assert client(host_a).get(path + str(event_a)).status_code == 401
    assert participant.delete('/api/v1/session').status_code == 403
    assert participant.delete('/api/v1/session', headers={'x-csrf-token': participant.cookies.get('__Host-fm_csrf'), 'origin': 'https://evil.test'}).status_code == 403
    assert participant.delete('/api/v1/session', headers={'x-csrf-token': participant.cookies.get('__Host-fm_csrf')}).status_code == 204
    assert participant.get(path + str(event_a)).status_code == 401
    stolen = client(host_a)
    stolen.cookies.set('__Host-fm_session', old_session, domain=host_a, path='/')
    assert stolen.get(path + str(event_a)).status_code == 401
    cross_host = client(host_b)
    cross_host.cookies.set('__Host-fm_session', old_session, domain=host_b, path='/')
    assert cross_host.get(path + str(event_b)).status_code == 401
    with psycopg.connect(ADMIN) as conn:
        conn.execute("UPDATE app_sessions SET expires_at = now() - interval '1 second' WHERE user_id = %s", (users[admin_subject],))
    assert admin.get(path + str(draft_a)).status_code == 401

import os
from io import BytesIO
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.api import tenant_admin
from app.api.app_session import get_google_verifier, router as session_router
from app.api.gallery_limit import LogoUploadLimit
from app.api.tenant_context import router as context_router
from app.core.config import settings
from app.db.migrate import migrate
from app.db.provision_context import provision as provision_runtime
from app.db.provision_tenant import provision as provision_tenant
from app.db.session import tenant_session

ADMIN, RUNTIME = os.getenv('TEST_DATABASE_ADMIN_URL'), os.getenv('TEST_DATABASE_RUNTIME_URL')
pytestmark = pytest.mark.skipif(not ADMIN or not RUNTIME, reason='disposable PostgreSQL URLs not configured')
SESSION_COOKIE, CSRF_COOKIE, V1 = '__Host-fm_session', '__Host-fm_csrf', '/api/v1'


def png(size=(40, 20), color=(200, 30, 30, 255)):
    out = BytesIO()
    Image.new('RGBA', size, color).save(out, format='PNG')
    return out.getvalue()


@pytest.fixture
def world(monkeypatch):
    migrate(ADMIN)
    with psycopg.connect(RUNTIME) as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
    with psycopg.connect(ADMIN) as conn:  # other tests grant broad table privileges to this role
        conn.execute(sql.SQL('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}').format(sql.Identifier(role)))
    provision_runtime(ADMIN, role)
    monkeypatch.setattr(settings, 'DATABASE_URL', RUNTIME)
    suffix = uuid4().hex[:10]
    tenants = {}
    for key in ('a', 'b'):
        info = provision_tenant(ADMIN, f'Tenant {key}', f'{key}-{suffix}', f'{key}-{suffix}.example.test', f'owner-{key}-{suffix}@example.test')
        tenants[key] = {'id': info['tenant_id'], 'host': info['hostname'], 'email': f'owner-{key}-{suffix}@example.test'}
    app = FastAPI()
    app.add_middleware(LogoUploadLimit)
    for router in (session_router, tenant_admin.router, tenant_admin.public_router, context_router):
        app.include_router(router, prefix=V1)
    state = {}
    app.dependency_overrides[get_google_verifier] = lambda: lambda token: {
        'sub': token, 'nonce': state['nonce'], 'email': state['emails'].get(token), 'email_verified': state['verified'].get(token, True)}
    state['emails'], state['verified'] = {}, {}

    def client(host):
        return TestClient(app, base_url=f'https://{host}', headers={'origin': f'https://{host}'})

    def login(host, subject, email=None, verified=True):
        state['emails'][subject], state['verified'][subject] = email, verified
        c = client(host)
        state['nonce'] = c.post(f'{V1}/session/challenge').json()['nonce']
        assert c.post(f'{V1}/session/google', json={'id_token': subject}).status_code == 200
        return c

    def mutate(c, method, path, **kwargs):
        headers = kwargs.pop('headers', {})
        headers.setdefault('x-csrf-token', c.cookies.get(CSRF_COOKIE))
        return c.request(method, V1 + path, headers=headers, **kwargs)

    return {'tenants': tenants, 'client': client, 'login': login, 'mutate': mutate, 'suffix': suffix}


def test_invitation_binds_owner_to_verified_email_only(world):
    a, b = world['tenants']['a'], world['tenants']['b']
    login = world['login']
    # Same email but unverified (e.g. a spoofed claim) never becomes a member.
    impostor = login(a['host'], 'impostor-' + world['suffix'], a['email'], verified=False)
    assert impostor.get(f'{V1}/admin/access').status_code == 403
    # Verified email of A's invited owner has no power on tenant B.
    assert login(b['host'], 'cross-' + world['suffix'], a['email']).get(f'{V1}/admin/access').status_code == 403
    owner = login(a['host'], 'owner-a-' + world['suffix'], a['email'])
    assert owner.get(f'{V1}/admin/access').json() == {'role': 'owner'}
    # The impostor session predates the claim but is a different user: still denied.
    assert impostor.get(f'{V1}/admin/access').status_code == 403
    with psycopg.connect(ADMIN) as conn:
        assert conn.execute("SELECT claimed_by IS NOT NULL FROM tenant_invitations WHERE tenant_id = %s", (a['id'],)).fetchone() == (True,)
        # A claimed invitation cannot be replayed by another account with the same verified email.
        conn.execute("DELETE FROM tenant_memberships WHERE tenant_id = %s", (a['id'],))
    assert login(a['host'], 'second-' + world['suffix'], a['email']).get(f'{V1}/admin/access').status_code == 403
    # Expired invitations are not claimable; re-running provisioning refreshes them.
    with psycopg.connect(ADMIN) as conn:
        conn.execute("UPDATE tenant_invitations SET claimed_at = NULL, claimed_by = NULL, expires_at = now() - interval '1 second' WHERE tenant_id = %s", (a['id'],))
    assert login(a['host'], 'late-' + world['suffix'], a['email']).get(f'{V1}/admin/access').status_code == 403
    with pytest.raises(ValueError, match='slug already exists'):  # reviving an expired invitation needs the flag
        provision_tenant(ADMIN, 'Tenant a', f"a-{world['suffix']}", a['host'], a['email'])
    assert login(a['host'], 'still-late-' + world['suffix'], a['email']).get(f'{V1}/admin/access').status_code == 403
    provision_tenant(ADMIN, 'Tenant a', f"a-{world['suffix']}", a['host'], a['email'], existing_tenant_id=a['id'])
    assert login(a['host'], 'fresh-' + world['suffix'], a['email']).get(f'{V1}/admin/access').json() == {'role': 'owner'}


def test_admin_api_isolation_roles_csrf_and_branding(world):
    a, b = world['tenants']['a'], world['tenants']['b']
    login, mutate, client, suffix = world['login'], world['mutate'], world['client'], world['suffix']
    owner_a = login(a['host'], 'owner-a-' + suffix, a['email'])
    owner_b = login(b['host'], 'owner-b-' + suffix, b['email'])
    participant = login(a['host'], 'participant-' + suffix)
    admin_a2 = login(a['host'], 'admin2-' + suffix)
    with psycopg.connect(ADMIN) as conn:
        uid = conn.execute('SELECT id FROM users WHERE google_subject = %s', ('admin2-' + suffix,)).fetchone()[0]
        conn.execute("INSERT INTO tenant_memberships VALUES (%s, %s, 'admin')", (a['id'], uid))
    assert admin_a2.get(f'{V1}/admin/access').json() == {'role': 'admin'}

    # Participants and anonymous callers cannot use any admin route.
    anonymous = client(a['host'])
    for c, status in ((participant, 403), (anonymous, 401)):
        assert c.get(f'{V1}/admin/events').status_code == status
        assert c.get(f'{V1}/admin/branding').status_code == status
        if c is participant:
            assert mutate(c, 'POST', '/admin/events', json={'name': 'X', 'slug': 'xxx'}).status_code == 403
            assert mutate(c, 'PUT', '/admin/branding', json={'palette': 'ocean'}).status_code == 403
            assert mutate(c, 'PUT', '/admin/branding/logo', files={'logo': ('l.png', png(), 'image/png')}).status_code == 403
        else:
            assert anonymous.post(f'{V1}/admin/events', json={'name': 'X', 'slug': 'xxx'}).status_code in (401, 403)

    # CSRF and Origin are required on every mutation.
    body = {'name': 'Corrida 2027', 'slug': 'corrida'}
    assert owner_a.post(f'{V1}/admin/events', json=body).status_code == 403
    assert owner_a.post(f'{V1}/admin/events', json=body, headers={'x-csrf-token': 'wrong'}).status_code == 403
    assert mutate(owner_a, 'POST', '/admin/events', json=body, headers={'origin': 'https://evil.test'}).status_code == 403

    created = mutate(owner_a, 'POST', '/admin/events', json=body)
    assert created.status_code == 201 and created.json()['status'] == 'draft'
    event_a = created.json()['id']
    assert mutate(owner_a, 'POST', '/admin/events', json=body).status_code == 409
    assert mutate(owner_a, 'POST', '/admin/events', json={**body, 'slug': 'Bad Slug'}).status_code == 422
    assert mutate(owner_a, 'POST', '/admin/events', json={**body, 'tenant_id': b['id']}).status_code == 422
    event_b = mutate(owner_b, 'POST', '/admin/events', json={'name': 'Festival', 'slug': 'corrida'}).json()['id']
    listing = owner_a.get(f'{V1}/admin/events').json()['events']
    assert [e['id'] for e in listing] == [event_a]  # includes drafts, excludes B
    assert admin_a2.get(f'{V1}/admin/events').json()['events'][0]['id'] == event_a

    # Draft is invisible to participants until published; unpublishing hides it again.
    assert participant.get(f'{V1}/events/{event_a}').status_code == 404
    with psycopg.connect(ADMIN) as conn:
        conn.execute('INSERT INTO event_participations (tenant_id, event_id, user_id) SELECT %s, %s, id FROM users WHERE google_subject = %s', (a['id'], event_a, 'participant-' + suffix))
    assert mutate(owner_a, 'POST', f'/admin/events/{event_a}/publish').json()['status'] == 'published'
    assert participant.get(f'{V1}/events/{event_a}').status_code == 200
    assert mutate(owner_a, 'POST', f'/admin/events/{event_a}/publish').status_code == 409
    assert mutate(owner_a, 'POST', f'/admin/events/{event_a}/unpublish').json()['status'] == 'draft'
    assert participant.get(f'{V1}/events/{event_a}').status_code == 404
    updated = mutate(owner_a, 'PATCH', f'/admin/events/{event_a}', json={'name': 'Corrida 2028', 'description': 'Rua'})
    assert updated.json()['name'] == 'Corrida 2028' and updated.json()['slug'] == 'corrida'
    assert mutate(owner_a, 'PATCH', f'/admin/events/{event_a}', json={}).status_code == 422
    assert mutate(owner_a, 'PATCH', f'/admin/events/{event_a}', json={'name': None}).status_code == 422
    assert mutate(owner_a, 'POST', f'/admin/events/{event_a}/close').json()['status'] == 'closed'
    assert mutate(owner_a, 'POST', f'/admin/events/{event_a}/publish').json()['status'] == 'published'

    # Tenant A's admin cannot touch B's event even with B's id on A's host.
    assert owner_a.get(f'{V1}/admin/events/{event_b}').status_code == 404
    for method, path, kwargs in (('PATCH', f'/admin/events/{event_b}', {'json': {'name': 'Hacked'}}),
                                 ('POST', f'/admin/events/{event_b}/publish', {}),
                                 ('POST', f'/admin/events/{event_b}/unpublish', {}),
                                 ('POST', f'/admin/events/{event_b}/close', {})):
        assert mutate(owner_a, method, path, **kwargs).status_code == 404
    with psycopg.connect(ADMIN) as conn:
        assert conn.execute('SELECT name, status FROM events WHERE id = %s', (event_b,)).fetchone() == ('Festival', 'draft')
    # A's session cookie is useless on B's hostname.
    stolen = client(b['host'])
    stolen.cookies.set(SESSION_COOKIE, owner_a.cookies.get(SESSION_COOKIE), domain=b['host'], path='/')
    assert stolen.get(f'{V1}/admin/events').status_code == 401
    assert owner_b.get(f'{V1}/admin/events/{event_a}').status_code == 404

    # Branding: predefined palettes only; the public context reflects the result.
    assert mutate(owner_a, 'PUT', '/admin/branding', json={'palette': 'nope'}).status_code == 422
    assert mutate(owner_a, 'PUT', '/admin/branding', json={'palette': 'ocean', 'colors': {'primary': 'red'}}).status_code == 422
    assert mutate(owner_a, 'PUT', '/admin/branding', json={'palette': 'ocean'}).json()['colors']['primary'] == '#0b5fa5'
    assert owner_a.get(f'{V1}/tenant/context').json()['branding']['palette'] == 'ocean'
    assert owner_b.get(f'{V1}/admin/branding').json()['palette'] == 'violet'

    # Logo: raster only, decoded and re-encoded, scoped to the tenant host.
    assert mutate(owner_a, 'PUT', '/admin/branding/logo', files={'logo': ('l.svg', b'<svg xmlns="http://www.w3.org/2000/svg"/>', 'image/svg+xml')}).status_code == 422
    assert mutate(owner_a, 'PUT', '/admin/branding/logo', files={'logo': ('l.png', b'\x89PNG\r\n\x1a\nnot an image', 'image/png')}).status_code == 422
    assert mutate(owner_a, 'PUT', '/admin/branding/logo', files={'logo': ('l.png', b'x' * (1024 * 1024 + 70000), 'image/png')}).status_code == 413
    assert mutate(owner_a, 'PUT', '/admin/branding/logo', files={'logo': ('l.png', png((900, 300)), 'image/png')}).status_code == 200
    ctx = owner_a.get(f'{V1}/tenant/context').json()['branding']
    token_a = ctx['logo_url'].rsplit('/', 1)[1].removesuffix('.png')
    assert ctx['logo_url'] == f'/api/v1/tenant/logo/{token_a}.png' and len(token_a) == 32
    assert owner_a.get(f'{V1}/admin/branding').json()['logo_url'] == ctx['logo_url']
    served = anonymous.get(ctx['logo_url'])
    assert served.status_code == 200 and served.headers['content-type'] == 'image/png'
    assert served.headers['x-content-type-options'] == 'nosniff' and 'immutable' in served.headers['cache-control']
    assert Image.open(BytesIO(served.content)).size == (512, 171)
    # Conditional requests are honoured.
    cached = anonymous.get(ctx['logo_url'], headers={'if-none-match': served.headers['etag']})
    assert cached.status_code == 304 and not cached.content
    assert anonymous.get(ctx['logo_url'], headers={'if-none-match': '"other"'}).status_code == 200
    # Token of A's logo on B's host never works, and B has no logo.
    assert client(b['host']).get(ctx['logo_url']).status_code == 404
    assert owner_b.get(f'{V1}/tenant/context').json()['branding']['logo_url'] is None
    assert owner_b.get(f'{V1}/admin/branding').json()['logo_url'] is None
    # Wrong / malformed tokens: 404 and never cacheable.
    for bad in ('0' * 32, 'zz', token_a[:-1], token_a.upper()):
        miss = anonymous.get(f'{V1}/tenant/logo/{bad}.png')
        assert miss.status_code == 404 and miss.headers['cache-control'] == 'no-store'
    # Replacing the logo invalidates the previous URL; removing it kills the current one.
    assert mutate(owner_a, 'PUT', '/admin/branding/logo', files={'logo': ('l.png', png((50, 50), (1, 2, 3, 255)), 'image/png')}).status_code == 200
    new_url = owner_a.get(f'{V1}/admin/branding').json()['logo_url']
    assert new_url != ctx['logo_url']
    stale = anonymous.get(ctx['logo_url'])
    assert stale.status_code == 404 and stale.headers['cache-control'] == 'no-store'
    assert anonymous.get(new_url).status_code == 200
    assert mutate(owner_a, 'DELETE', '/admin/branding/logo').json()['logo_url'] is None
    assert anonymous.get(new_url).status_code == 404
    with psycopg.connect(ADMIN) as conn:
        assert conn.execute('SELECT palette, theme_version FROM tenant_branding WHERE tenant_id = %s', (b['id'],)).fetchone() == ('violet', 1)


def test_rls_blocks_cross_tenant_writes_for_runtime_role(world):
    a, b = world['tenants']['a'], world['tenants']['b']
    event_b, user = uuid4(), uuid4()
    with psycopg.connect(ADMIN) as conn:
        conn.execute("INSERT INTO events (id, tenant_id, name, slug) VALUES (%s, %s, 'B', 'b-event')", (event_b, b['id']))
        conn.execute('INSERT INTO users (id, google_subject) VALUES (%s, %s)', (user, str(user)))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_session(RUNTIME, a['id']) as conn:
            conn.execute("INSERT INTO events (id, tenant_id, name, slug) VALUES (%s, %s, 'x', 'x-event')", (uuid4(), b['id']))
    with tenant_session(RUNTIME, a['id']) as conn:
        assert conn.execute("UPDATE events SET name = 'Hacked' WHERE id = %s", (event_b,)).rowcount == 0
        assert conn.execute("UPDATE tenant_branding SET palette = 'sunset' WHERE tenant_id = %s", (b['id'],)).rowcount == 0
        assert conn.execute('SELECT count(*) FROM events WHERE tenant_id = %s', (b['id'],)).fetchone() == (0,)
        assert conn.execute('SELECT count(*) FROM tenant_branding WHERE tenant_id = %s', (b['id'],)).fetchone() == (0,)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_session(RUNTIME, a['id']) as conn:
            conn.execute("INSERT INTO tenant_branding (tenant_id, palette) VALUES (%s, 'sunset') ON CONFLICT (tenant_id) DO UPDATE SET palette = 'sunset'", (b['id'],))
    # No context at all denies everything, and runtime cannot mint memberships or read invitations.
    with psycopg.connect(RUNTIME) as conn:
        assert conn.execute('SELECT count(*) FROM events').fetchone() == (0,)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_session(RUNTIME, a['id']) as conn:
            conn.execute("INSERT INTO tenant_memberships VALUES (%s, %s, 'owner')", (a['id'], user))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_session(RUNTIME, a['id']) as conn:
            conn.execute('SELECT * FROM tenant_invitations')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_session(RUNTIME, a['id']) as conn:
            conn.execute('DELETE FROM events')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_session(RUNTIME, a['id']) as conn:
            conn.execute('INSERT INTO tenants (id, name, slug) VALUES (%s, %s, %s)', (uuid4(), 'x', 'xxx-slug'))


def test_provisioning_cli_is_idempotent_validated_and_not_http(world):
    suffix = uuid4().hex[:8]
    args = ('Aurora', f'aurora-{suffix}', f'aurora-{suffix}.example.test', f'Owner-{suffix}@Example.test')
    first = provision_tenant(ADMIN, *args)
    second = provision_tenant(ADMIN, *args)
    assert first['tenant_id'] == second['tenant_id'] and first['created'] is True and second['created'] is False
    with psycopg.connect(ADMIN) as conn:
        tid = first['tenant_id']
        assert conn.execute('SELECT count(*) FROM tenants WHERE slug = %s', (args[1],)).fetchone() == (1,)
        assert conn.execute('SELECT count(*) FROM tenant_domains WHERE tenant_id = %s', (tid,)).fetchone() == (1,)
        assert conn.execute('SELECT count(*), min(palette) FROM tenant_branding WHERE tenant_id = %s', (tid,)).fetchone() == (1, 'violet')
        assert conn.execute('SELECT email, role FROM tenant_invitations WHERE tenant_id = %s', (tid,)).fetchall() == [(args[3].lower(), 'owner')]
        assert conn.execute('SELECT count(*) FROM tenant_memberships WHERE tenant_id = %s', (tid,)).fetchone() == (0,)
    # Another tenant cannot take over the hostname.
    with pytest.raises(ValueError, match='hostname already belongs'):
        provision_tenant(ADMIN, 'Other', f'other-{suffix}', args[2], 'other@example.test')
    bad = [('N', 'admin', 'x.example.test', 'o@example.test'), ('N', 'api', 'x.example.test', 'o@example.test'),
           ('N', 'Bad_Slug', 'x.example.test', 'o@example.test'), ('N', 'ab', 'x.example.test', 'o@example.test'),
           ('N', 'good-slug', 'admin.example.test', 'o@example.test'), ('N', 'good-slug', 'www.example.test', 'o@example.test'),
           ('N', 'good-slug', 'localhost', 'o@example.test'), ('N', 'good-slug', 'UPPER.example.test', 'o@example.test'),
           ('N', 'good-slug', 'a_b.example.test', 'o@example.test'), ('N', 'good-slug', 'x.example.test', 'not-an-email'),
           ('', 'good-slug', 'x.example.test', 'o@example.test')]
    for item in bad:
        with pytest.raises(ValueError):
            provision_tenant(ADMIN, *item)
    # The runtime role cannot provision at all.
    with pytest.raises(ValueError, match='migration-owner'):
        provision_tenant(RUNTIME, 'Z', f'zeta-{suffix}', f'zeta-{suffix}.example.test', 'z@example.test')
    # No HTTP route can create tenants or organizers.
    from app.main import app
    # Every mutating route is enumerated; tenant creation is not among them, and any new
    # route must be added here consciously. Routes that touch tenant data sit under /admin.
    mutating = sorted(f'{method.upper()} {path}' for path, item in app.openapi()['paths'].items()
                      for method in item if method in ('post', 'put', 'patch', 'delete'))
    assert mutating == sorted([
        'POST /api/v1/folders/index', 'POST /api/v1/folders/{folder_id}/search', 'POST /api/v1/scan', 'POST /api/v1/auth/google/callback',
        'POST /api/v1/session/challenge', 'POST /api/v1/session/google', 'DELETE /api/v1/session',
        'POST /api/v1/events/{event_id}/gallery/index', 'POST /api/v1/events/{event_id}/gallery/search',
        'POST /api/v1/admin/events', 'PATCH /api/v1/admin/events/{event_id}', 'POST /api/v1/admin/events/{event_id}/publish',
        'POST /api/v1/admin/events/{event_id}/unpublish', 'POST /api/v1/admin/events/{event_id}/close',
        'PUT /api/v1/admin/branding', 'PUT /api/v1/admin/branding/logo', 'DELETE /api/v1/admin/branding/logo'])
    assert not [p for p in app.openapi()['paths'] if any(w in p for w in ('provision', 'organizer', '/tenants', 'invitation', 'membership'))]
    # And the runtime role has no table privilege to create tenants or memberships itself.
    with psycopg.connect(ADMIN) as conn:
        with psycopg.connect(RUNTIME) as rt:
            role = rt.execute('SELECT current_user').fetchone()[0]
        for table, privilege in (('tenants', 'INSERT'), ('tenants', 'UPDATE'), ('tenant_domains', 'INSERT'), ('tenant_memberships', 'INSERT'),
                                 ('tenant_memberships', 'UPDATE'), ('tenant_invitations', 'INSERT'), ('tenant_invitations', 'SELECT'), ('events', 'DELETE')):
            assert not conn.execute('SELECT has_table_privilege(%s, %s, %s)', (role, f'public.{table}', privilege)).fetchone()[0], (table, privilege)


def test_existing_slug_is_never_taken_over_implicitly(world):
    suffix = uuid4().hex[:8]
    slug, host, owner = f'taken-{suffix}', f'taken-{suffix}.example.test', f'real-{suffix}@example.test'
    info = provision_tenant(ADMIN, 'Taken', slug, host, owner)
    tid = info['tenant_id']
    stranger = f'stranger-{suffix}@example.test'
    # A new hostname and/or a different owner for an existing slug is refused by default.
    for args in (('Taken', slug, f'evil-{suffix}.example.test', stranger), ('Taken', slug, host, stranger), ('Taken', slug, f'evil-{suffix}.example.test', owner)):
        with pytest.raises(ValueError, match='slug already exists'):
            provision_tenant(ADMIN, *args)
    with psycopg.connect(ADMIN) as conn:
        assert conn.execute('SELECT email FROM tenant_invitations WHERE tenant_id = %s', (tid,)).fetchall() == [(owner,)]
        assert conn.execute('SELECT count(*) FROM tenant_domains WHERE tenant_id = %s', (tid,)).fetchone() == (1,)
    # The explicit id must match.
    with pytest.raises(ValueError, match='does not match'):
        provision_tenant(ADMIN, 'Taken', slug, host, stranger, existing_tenant_id=str(uuid4()))
    with pytest.raises(ValueError, match='UUID'):
        provision_tenant(ADMIN, 'Taken', slug, host, stranger, existing_tenant_id='nope')
    # Explicit confirmation adds the owner and revokes the other pending invitation.
    result = provision_tenant(ADMIN, 'Taken', slug, f'second-{suffix}.example.test', stranger, existing_tenant_id=tid)
    assert result['created'] is False and result['owner_invited'] is True
    with psycopg.connect(ADMIN) as conn:
        rows = dict(conn.execute('SELECT email, revoked_at IS NULL FROM tenant_invitations WHERE tenant_id = %s', (tid,)).fetchall())
        assert rows == {owner: False, stranger: True}
        assert conn.execute('SELECT count(*) FROM tenant_domains WHERE tenant_id = %s', (tid,)).fetchone() == (2,)
        conn.execute("UPDATE tenants SET status = 'suspended' WHERE id = %s", (tid,))
    with pytest.raises(ValueError, match='suspended'):
        provision_tenant(ADMIN, 'Taken', slug, host, owner)
    with pytest.raises(ValueError, match='suspended'):
        provision_tenant(ADMIN, 'Taken', slug, host, owner, existing_tenant_id=tid)


def test_owner_invitation_upgrades_existing_admin(world):
    a = world['tenants']['a']
    subject = 'upgrade-' + world['suffix']
    email = f'upgrade-{world["suffix"]}@example.test'
    first = world['login'](a['host'], subject, email)
    assert first.get(f'{V1}/admin/access').status_code == 403
    with psycopg.connect(ADMIN) as conn:
        uid = conn.execute('SELECT id FROM users WHERE google_subject = %s', (subject,)).fetchone()[0]
        conn.execute("INSERT INTO tenant_memberships VALUES (%s, %s, 'admin')", (a['id'], uid))
        conn.execute("INSERT INTO tenant_invitations (tenant_id, email, role, expires_at) VALUES (%s, %s, 'owner', now() + interval '1 day')", (a['id'], email))
    assert world['login'](a['host'], subject, email).get(f'{V1}/admin/access').json() == {'role': 'owner'}
    with psycopg.connect(ADMIN) as conn:
        assert conn.execute('SELECT claimed_by FROM tenant_invitations WHERE tenant_id = %s AND email = %s', (a['id'], email)).fetchone() == (uid,)


def test_claim_function_requires_matching_tenant_context(world):
    a, b = world['tenants']['a'], world['tenants']['b']
    subject = 'ctx-' + world['suffix']
    email = f'ctx-{world["suffix"]}@example.test'
    world['login'](a['host'], subject, email)
    with psycopg.connect(ADMIN) as conn:
        uid = conn.execute('SELECT id FROM users WHERE google_subject = %s', (subject,)).fetchone()[0]
        conn.execute("INSERT INTO tenant_invitations (tenant_id, email, role, expires_at) VALUES (%s, %s, 'owner', now() + interval '1 day')", (b['id'], email))
    for tenant_arg in (b['id'], None):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with tenant_session(RUNTIME, a['id']) as conn:
                conn.execute('SELECT public.claim_tenant_invitations(%s, %s)', (tenant_arg, uid))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with psycopg.connect(RUNTIME) as conn:  # no context at all
            conn.execute('SELECT public.claim_tenant_invitations(%s, %s)', (b['id'], uid))
    with psycopg.connect(ADMIN) as conn:
        assert conn.execute('SELECT claimed_at FROM tenant_invitations WHERE tenant_id = %s AND email = %s', (b['id'], email)).fetchone() == (None,)
        assert conn.execute('SELECT count(*) FROM tenant_memberships WHERE tenant_id = %s AND user_id = %s', (b['id'], uid)).fetchone() == (0,)


def test_large_noisy_logo_is_fitted_not_500(world):
    import random
    a = world['tenants']['a']
    owner = world['login'](a['host'], 'noisy-' + world['suffix'], a['email'])  # claims A's owner invitation
    noisy = Image.frombytes('RGB', (1024, 1024), random.Random(1).randbytes(1024 * 1024 * 3))
    for quality in (80, 60, 40, 20):
        out = BytesIO()
        noisy.save(out, format='JPEG', quality=quality)
        if len(out.getvalue()) < 1024 * 1024:
            break
    assert len(out.getvalue()) < 1024 * 1024
    response = world['mutate'](owner, 'PUT', '/admin/branding/logo', files={'logo': ('n.jpg', out.getvalue(), 'image/jpeg')})
    assert response.status_code == 200
    with psycopg.connect(ADMIN) as conn:
        assert 0 < conn.execute('SELECT octet_length(logo_png) FROM tenant_branding WHERE tenant_id = %s', (a['id'],)).fetchone()[0] <= 500_000


def test_event_text_validation_and_column_privileges(world):
    a, b = world['tenants']['a'], world['tenants']['b']
    owner = world['login'](a['host'], 'owner-a-' + world['suffix'], a['email'])
    mutate = world['mutate']
    ok = mutate(owner, 'POST', '/admin/events', json={'name': '  Padded  ', 'slug': 'padded', 'description': ' text '})
    assert ok.status_code == 201 and ok.json()['name'] == 'Padded' and ok.json()['description'] == 'text'
    for body in ({'name': '   ', 'slug': 'blank'}, {'name': 'a\x00b', 'slug': 'nul'}, {'name': 'a\nb', 'slug': 'nl'},
                 {'name': 'ok', 'slug': 'desc', 'description': 'x\x00y'}, {'name': 'ok', 'slug': 'esc', 'description': 'x\x1by'},
                 {'name': 'ok', 'slug': 'trailing\n'}):
        assert mutate(owner, 'POST', '/admin/events', json=body).status_code == 422, body
    event = ok.json()['id']
    for body in ({'name': '   '}, {'name': 'a\x00'}, {'description': 'a\x00'}, {'slug': 'x\x00'}):
        assert mutate(owner, 'PATCH', f'/admin/events/{event}', json=body).status_code == 422, body
    assert mutate(owner, 'PATCH', f'/admin/events/{event}', json={'description': 'line1\nline2'}).status_code == 200
    # Runtime UPDATE is column-level, even after a broad grant is re-run away by provision_context.
    with psycopg.connect(RUNTIME) as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
    with psycopg.connect(ADMIN) as conn:
        conn.execute(sql.SQL('GRANT UPDATE, INSERT ON public.events, public.tenant_branding TO {}').format(sql.Identifier(role)))
    provision_runtime(ADMIN, role)
    with psycopg.connect(ADMIN) as conn:
        def can(kind, table, column):
            return conn.execute('SELECT has_column_privilege(%s, %s, %s, %s)', (role, f'public.{table}', column, kind)).fetchone()[0]
        assert not can('UPDATE', 'events', 'tenant_id') and not can('UPDATE', 'events', 'id') and not can('UPDATE', 'events', 'created_at')
        assert not can('UPDATE', 'tenant_branding', 'tenant_id') and not can('UPDATE', 'tenant_branding', 'logo_url')
        assert not can('INSERT', 'tenant_branding', 'logo_url') and not can('INSERT', 'events', 'status')
        assert all(can('UPDATE', 'events', c) for c in ('name', 'slug', 'description', 'status', 'updated_at'))
        assert all(can('UPDATE', 'tenant_branding', c) for c in ('palette', 'colors', 'logo_png', 'theme_version'))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_session(RUNTIME, a['id']) as conn:
            conn.execute('UPDATE events SET tenant_id = %s WHERE id = %s', (b['id'], event))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_session(RUNTIME, a['id']) as conn:
            conn.execute("UPDATE tenant_branding SET logo_url = 'https://evil.test/x.png' WHERE tenant_id = %s", (a['id'],))


def _fresh_tenant(world, owner):
    key = uuid4().hex[:8]
    info = provision_tenant(ADMIN, 'Fresh', f'fresh-{key}', f'fresh-{key}.example.test', owner)
    return info, f'fresh-{key}', f'fresh-{key}.example.test'


def test_flagless_rerun_cannot_revive_corrected_typo_invitation(world):
    login, key = world['login'], uuid4().hex[:8]
    typo, right = f'typo-{key}@example.test', f'right-{key}@example.test'
    info, slug, host = _fresh_tenant(world, typo)
    tid = info['tenant_id']
    provision_tenant(ADMIN, 'Fresh', slug, host, right, existing_tenant_id=tid)  # operator corrects the address
    with pytest.raises(ValueError, match='slug already exists'):  # the original flagless command no longer works
        provision_tenant(ADMIN, 'Fresh', slug, host, typo)
    with psycopg.connect(ADMIN) as conn:
        rows = {e: (r is not None, x) for e, r, x in conn.execute('SELECT email, revoked_at, expires_at > now() FROM tenant_invitations WHERE tenant_id = %s', (tid,))}
    assert rows == {typo: (True, True), right: (False, True)}  # typo revoked (not merely expired); right untouched and live
    assert login(host, 'typo-' + key, typo).get(f'{V1}/admin/access').status_code == 403
    assert login(host, 'right-' + key, right).get(f'{V1}/admin/access').json() == {'role': 'owner'}
    # A flagless run for the live-then-claimed new owner is a harmless verification and changes nothing.
    assert provision_tenant(ADMIN, 'Fresh', slug, host, right)['owner_invited'] is False


def test_flagless_rerun_cannot_reinstate_removed_old_owner(world):
    login, key = world['login'], uuid4().hex[:8]
    old, new = f'old-{key}@example.test', f'new-{key}@example.test'
    info, slug, host = _fresh_tenant(world, old)
    tid = info['tenant_id']
    assert login(host, 'old-' + key, old).get(f'{V1}/admin/access').json() == {'role': 'owner'}
    provision_tenant(ADMIN, 'Fresh', slug, host, new, existing_tenant_id=tid)
    with psycopg.connect(ADMIN) as conn:
        conn.execute('DELETE FROM tenant_memberships WHERE tenant_id = %s AND user_id = (SELECT id FROM users WHERE google_subject = %s)', (tid, 'old-' + key))
    with pytest.raises(ValueError, match='slug already exists'):
        provision_tenant(ADMIN, 'Fresh', slug, host, old)
    assert login(host, 'old-' + key, old).get(f'{V1}/admin/access').status_code == 403
    assert login(host, 'new-' + key, new).get(f'{V1}/admin/access').json() == {'role': 'owner'}


def test_surrogate_and_invisible_names_are_rejected_not_500(world):
    a = world['tenants']['a']
    owner = world['login'](a['host'], 'owner-a-' + world['suffix'], a['email'])
    headers = {'x-csrf-token': owner.cookies.get(CSRF_COOKIE), 'content-type': 'application/json'}
    for raw in ('{"name":"a\\ud800b","slug":"sur"}', '{"name":"ok","slug":"sur","description":"x\\udc00"}',
                '{"name":"\\u200b\\u200d","slug":"zw"}', '{"name":"\\u200b \\u2060","slug":"zw2"}'):
        response = owner.post(f'{V1}/admin/events', content=raw, headers=headers)
        assert response.status_code == 422, raw
    ok = owner.post(f'{V1}/admin/events', content='{"name":"Caf\\u00e9 \\u200d","slug":"cafe"}', headers=headers)
    assert ok.status_code == 201


def test_provision_context_is_authoritative_over_preexisting_grants(world):
    with psycopg.connect(RUNTIME) as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
    tables = ('events', 'tenant_branding', 'tenants', 'tenant_domains', 'tenant_memberships', 'tenant_invitations')
    with psycopg.connect(ADMIN) as conn:
        for table in tables:
            conn.execute(sql.SQL('GRANT ALL ON public.{} TO {}').format(sql.Identifier(table), sql.Identifier(role)))
    provision_runtime(ADMIN, role)  # after the grants committed
    with psycopg.connect(ADMIN) as conn:
        granted = {(t, p) for t in tables for p in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER')
                   if conn.execute('SELECT has_table_privilege(%s, %s, %s)', (role, f'public.{t}', p)).fetchone()[0]}
        columns = {(t, c, k) for t, c in (('events', 'name'), ('events', 'tenant_id'), ('tenant_branding', 'logo_png'), ('tenant_branding', 'logo_url'))
                   for k in ('INSERT', 'UPDATE')
                   if conn.execute('SELECT has_column_privilege(%s, %s, %s, %s)', (role, f'public.{t}', c, k)).fetchone()[0]}
    # Only SELECT remains at table level on these; writes are column-level for events/branding.
    assert granted == {('events', 'SELECT'), ('tenant_branding', 'SELECT'), ('tenants', 'SELECT'), ('tenant_memberships', 'SELECT')}
    assert columns == {('events', 'name', 'UPDATE'), ('tenant_branding', 'logo_png', 'INSERT'), ('tenant_branding', 'logo_png', 'UPDATE')} | {('events', 'name', 'INSERT'), ('events', 'tenant_id', 'INSERT')}


def test_logo_etag_accepts_weak_validators(world):
    a = world['tenants']['a']
    owner = world['login'](a['host'], 'owner-a-' + world['suffix'], a['email'])
    assert world['mutate'](owner, 'PUT', '/admin/branding/logo', files={'logo': ('l.png', png(), 'image/png')}).status_code == 200
    url = owner.get(f'{V1}/admin/branding').json()['logo_url']
    etag = owner.get(url).headers['etag']
    assert owner.get(url, headers={'if-none-match': 'W/' + etag}).status_code == 304
    assert owner.get(url, headers={'if-none-match': f'"x", W/{etag}'}).status_code == 304

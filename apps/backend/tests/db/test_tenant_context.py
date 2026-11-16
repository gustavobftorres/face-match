import os
from uuid import uuid4
import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.tenant_context import router
from app.core.config import settings
from app.db.migrate import migrate
from app.db.provision_context import provision

ADMIN = os.getenv('TEST_DATABASE_ADMIN_URL')
RUNTIME = os.getenv('TEST_DATABASE_RUNTIME_URL')
app = FastAPI()
app.include_router(router, prefix='/api/v1')

@pytest.mark.parametrize('headers', [[], [('host', 'admin.example.test')], [('host', 'api.example.test')], [('host', 'foo.example.test,bar.example.test')], [('host', 'foo.example.test.')], [('host', 'foo.example.test:99999')], [('host', 'foo.example.test:' + '9' * 5000)], [('host', 'foo.example.test'), ('host', 'bar.example.test')]])
def test_invalid_host_is_rejected(headers):
    client = TestClient(app)
    client.headers.pop('host', None)
    assert client.get('/api/v1/tenant/context', headers=headers).status_code == 404

@pytest.mark.skipif(not ADMIN or not RUNTIME, reason='disposable PostgreSQL URLs not configured')
def test_lookup_backfill_triggers_and_default_privileges():
    """Run against a fresh disposable database before any other migration test."""
    from pathlib import Path
    from psycopg import sql
    from app.db.provision_context import provision

    with psycopg.connect(RUNTIME) as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
    inherited_role = 'fm_lookup_test_' + uuid4().hex
    tenant_id, domain_id = uuid4(), uuid4()
    old, new = f'old-{uuid4().hex}.example.test', f'new-{uuid4().hex}.example.test'
    migration_dir = Path(__file__).resolve().parents[2] / 'app/db/migrations'
    with psycopg.connect(ADMIN) as conn:
        # This test requires a fresh database to exercise migration from 001 to 002.
        assert conn.execute("SELECT to_regclass('public.schema_migrations')").fetchone()[0] is None
        conn.execute((migration_dir / '001_tenant_foundation.sql').read_text())
        conn.execute('CREATE TABLE schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())')
        conn.execute("INSERT INTO schema_migrations (name) VALUES ('001_tenant_foundation.sql')")
        conn.execute("INSERT INTO tenants (id, name, slug) VALUES (%s, 'Old', %s)", (tenant_id, str(tenant_id)))
        conn.execute('INSERT INTO tenant_domains (id, tenant_id, hostname) VALUES (%s, %s, %s)', (domain_id, tenant_id, old))
        conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(inherited_role)))
        conn.execute(sql.SQL('GRANT {} TO {}').format(sql.Identifier(inherited_role), sql.Identifier(role)))
        conn.execute(sql.SQL('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {}').format(sql.Identifier(inherited_role)))
    migrate(ADMIN)
    with psycopg.connect(ADMIN) as conn:
        assert conn.execute('SELECT tenant_id FROM public.tenant_hostname_lookup WHERE hostname = %s', (old,)).fetchone() == (tenant_id,)
        assert not conn.execute("SELECT has_table_privilege(%s, 'public.tenant_hostname_lookup', 'SELECT')", (role,)).fetchone()[0]
        conn.execute(sql.SQL('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM {}').format(sql.Identifier(inherited_role)))
        conn.execute(sql.SQL('REVOKE {} FROM {}').format(sql.Identifier(inherited_role), sql.Identifier(role)))
        conn.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(inherited_role)))
        conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(inherited_role)))
    provision(ADMIN, role)
    with psycopg.connect(RUNTIME) as conn:
        assert conn.execute('SELECT public.lookup_tenant_hostname(%s)', (old,)).fetchone() == (tenant_id,)
        assert not conn.execute("SELECT has_table_privilege(current_user, 'public.tenant_hostname_lookup', 'SELECT')").fetchone()[0]
    with psycopg.connect(ADMIN) as conn:
        conn.execute('UPDATE tenant_domains SET hostname = %s WHERE id = %s', (new, domain_id))
    with psycopg.connect(RUNTIME) as conn:
        assert conn.execute('SELECT public.lookup_tenant_hostname(%s)', (old,)).fetchone() == (None,)
        assert conn.execute('SELECT public.lookup_tenant_hostname(%s)', (new,)).fetchone() == (tenant_id,)
    with psycopg.connect(ADMIN) as conn:
        conn.execute('DELETE FROM tenant_domains WHERE id = %s', (domain_id,))
    with psycopg.connect(RUNTIME) as conn:
        assert conn.execute('SELECT public.lookup_tenant_hostname(%s)', (new,)).fetchone() == (None,)


@pytest.mark.skipif(not ADMIN or not RUNTIME, reason='disposable PostgreSQL URLs not configured')
def test_public_context_uses_host_and_scoped_rls(monkeypatch):
    migrate(ADMIN)
    with psycopg.connect(RUNTIME) as conn:
        role = conn.execute('SELECT current_user').fetchone()[0]
        assert conn.execute('SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname = current_user').fetchone()[0]
    provision(ADMIN, role)
    suffix = uuid4().hex
    host_a, host_b, host_inactive = (f'{prefix}-{suffix}.example.test' for prefix in ('a', 'b', 'inactive'))
    a, b, inactive = uuid4(), uuid4(), uuid4()
    with psycopg.connect(ADMIN) as conn:
        for tid, name, host, status in ((a, 'Aurora', host_a, 'active'), (b, 'Horizonte', host_b, 'active'), (inactive, 'Inactive', host_inactive, 'suspended')):
            conn.execute('INSERT INTO tenants (id, name, slug, status) VALUES (%s, %s, %s, %s)', (tid, name, str(tid), status))
            conn.execute('INSERT INTO tenant_domains (id, tenant_id, hostname) VALUES (%s, %s, %s)', (uuid4(), tid, host))
            conn.execute('INSERT INTO tenant_branding (tenant_id, colors) VALUES (%s, %s)', (tid, psycopg.types.json.Jsonb({'primary': name})))
    monkeypatch.setattr(settings, 'DATABASE_URL', RUNTIME)
    client = TestClient(app)
    response = client.get('/api/v1/tenant/context', headers={'host': host_a.upper() + ':443', 'x-forwarded-host': host_b})
    assert response.status_code == 200
    assert response.json()['name'] == 'Aurora'
    assert response.json()['branding']['colors'] == {'primary': 'Aurora'}
    assert client.get('/api/v1/tenant/context', headers={'host': host_b}).json()['name'] == 'Horizonte'
    assert client.get('/api/v1/tenant/context', headers={'host': host_inactive}).status_code == 404
    assert client.get('/api/v1/tenant/context', headers={'host': 'unknown.example.test'}).status_code == 404
    with psycopg.connect(RUNTIME) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute('SELECT * FROM public.tenant_hostname_lookup')

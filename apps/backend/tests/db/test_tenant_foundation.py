"""Integration tests require an empty disposable PostgreSQL database and two URLs."""
import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from app.db.migrate import migrate
from app.db.session import tenant_session

ADMIN = os.getenv('TEST_DATABASE_ADMIN_URL')
RUNTIME = os.getenv('TEST_DATABASE_RUNTIME_URL')
pytestmark = pytest.mark.skipif(not ADMIN or not RUNTIME, reason='disposable PostgreSQL URLs not configured')


def test_tenant_isolation_and_global_identity():
    migrate(ADMIN)
    migrate(ADMIN)  # migrations are repeatable
    with psycopg.connect(RUNTIME) as runtime:
        role = runtime.execute('SELECT current_user').fetchone()[0]
        assert runtime.execute('SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname = current_user').fetchone()[0]
    a, b, user, event_a, event_b = (uuid4() for _ in range(5))
    with psycopg.connect(ADMIN) as admin:
        admin.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
        admin.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}').format(sql.Identifier(role)))
        admin.execute('INSERT INTO users (id, google_subject) VALUES (%s, %s)', (user, str(user)))
        admin.execute("INSERT INTO tenants (id, name, slug) VALUES (%s, 'A', %s), (%s, 'B', %s)", (a, str(a), b, str(b)))
    with tenant_session(RUNTIME, a) as conn:
        conn.execute("INSERT INTO tenant_memberships VALUES (%s, %s, 'owner')", (a, user))
        conn.execute("INSERT INTO events (id, tenant_id, name, slug) VALUES (%s, %s, 'A', 'event')", (event_a, a))
        conn.execute('INSERT INTO event_participations (tenant_id, event_id, user_id) VALUES (%s, %s, %s)', (a, event_a, user))
    with tenant_session(RUNTIME, b) as conn:
        conn.execute("INSERT INTO tenant_memberships VALUES (%s, %s, 'admin')", (b, user))
        conn.execute("INSERT INTO events (id, tenant_id, name, slug) VALUES (%s, %s, 'B', 'event')", (event_b, b))
        conn.execute('INSERT INTO event_participations (tenant_id, event_id, user_id) VALUES (%s, %s, %s)', (b, event_b, user))
        assert conn.execute('SELECT id FROM events').fetchall() == [(event_b,)]
        assert conn.execute('SELECT user_id FROM tenant_memberships').fetchall() == [(user,)]
        assert conn.execute('SELECT event_id FROM event_participations').fetchall() == [(event_b,)]
        assert conn.execute('SELECT count(*) FROM users WHERE id = %s', (user,)).fetchone() == (1,)
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with tenant_session(RUNTIME, b) as conn:
            conn.execute('INSERT INTO event_participations (tenant_id, event_id, user_id) VALUES (%s, %s, %s)', (b, event_a, user))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with tenant_session(RUNTIME, b) as conn:
            conn.execute("INSERT INTO events (id, tenant_id, name, slug) VALUES (%s, %s, 'bad', 'bad')", (uuid4(), a))
    with psycopg.connect(RUNTIME) as conn:
        assert conn.execute('SELECT * FROM events').fetchall() == []
        conn.commit()
        with conn.transaction():
            conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(a),))
            assert conn.execute('SELECT id FROM events').fetchall() == [(event_a,)]
        assert conn.execute('SELECT * FROM events').fetchall() == []

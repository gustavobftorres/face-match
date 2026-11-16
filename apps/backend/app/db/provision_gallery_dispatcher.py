"""Grant only the global pending-job relay function to a dedicated role."""
import os
import sys
import psycopg
from psycopg import sql


def provision(database_url, role):
    with psycopg.connect(database_url) as conn:
        flags = conn.execute('SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=%s', (role,)).fetchone()
        if flags is None or any(flags):
            raise ValueError('dispatcher role must exist without superuser or BYPASSRLS')
        identifier = sql.Identifier(role)
        conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(identifier))
        conn.execute(sql.SQL('GRANT EXECUTE ON FUNCTION public.gallery_pending_jobs() TO {}').format(identifier))


if __name__ == '__main__':
    provision(os.environ['DATABASE_URL'], sys.argv[1])

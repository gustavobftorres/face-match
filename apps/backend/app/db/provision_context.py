"""Grant the existing runtime role only the privileges needed for tenant context."""
import os
import sys

import psycopg
from psycopg import sql


def provision(database_url: str, runtime_role: str) -> None:
    with psycopg.connect(database_url) as connection:
        role = connection.execute(
            'SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = %s',
            (runtime_role,),
        ).fetchone()
        if role is None or any(role):
            raise ValueError('runtime role must exist and must not be superuser or BYPASSRLS')
        identifier = sql.Identifier(runtime_role)
        for statement in (
            'GRANT USAGE ON SCHEMA public TO {}',
            'GRANT SELECT ON public.tenants, public.tenant_branding TO {}',
            'GRANT EXECUTE ON FUNCTION public.lookup_tenant_hostname(text) TO {}',
            'REVOKE ALL ON public.tenant_hostname_lookup FROM {}',
        ):
            connection.execute(sql.SQL(statement).format(identifier))


if __name__ == '__main__':
    provision(os.environ['DATABASE_URL'], sys.argv[1])

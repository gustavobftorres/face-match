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
            # Authoritative for these tables: drop whatever earlier grants or default
            # privileges gave the role, then grant exactly what the code needs below.
            'REVOKE ALL ON public.events, public.tenant_branding, public.tenants, public.tenant_domains, '
            'public.tenant_memberships, public.tenant_invitations FROM {}',
            'GRANT USAGE ON SCHEMA public TO {}',
            'GRANT SELECT ON public.tenants, public.tenant_branding, public.events, public.tenant_memberships, public.event_participations TO {}',
            'GRANT SELECT, INSERT, UPDATE ON public.users TO {}',
            'GRANT SELECT, INSERT, DELETE ON public.login_challenges TO {}',
            'GRANT SELECT, INSERT, UPDATE ON public.app_sessions TO {}',
            'GRANT SELECT, INSERT, UPDATE, DELETE ON public.gallery_jobs, public.gallery_photos, public.gallery_searches, public.gallery_results TO {}',
            # Writes are column-level: only what the organizer API writes.
            'GRANT INSERT (id, tenant_id, name, slug, description) ON public.events TO {}',
            'GRANT UPDATE (name, slug, description, status, updated_at) ON public.events TO {}',
            'GRANT INSERT (tenant_id, palette, colors, logo_png) ON public.tenant_branding TO {}',
            'GRANT UPDATE (palette, colors, logo_png, theme_version) ON public.tenant_branding TO {}',
            'GRANT EXECUTE ON FUNCTION public.lookup_tenant_hostname(text) TO {}',
            'GRANT EXECUTE ON FUNCTION public.claim_tenant_invitations(uuid, uuid) TO {}',
            'REVOKE ALL ON public.tenant_hostname_lookup FROM {}',
        ):
            connection.execute(sql.SQL(statement).format(identifier))


if __name__ == '__main__':
    provision(os.environ['DATABASE_URL'], sys.argv[1])

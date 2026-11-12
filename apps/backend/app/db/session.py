"""Transaction-scoped tenant sessions for future API and worker entry points."""
from contextlib import contextmanager
from uuid import UUID

import psycopg


@contextmanager
def tenant_session(database_url: str, tenant_id: UUID):
    """Yield a connection in a transaction scoped to a server-authorized tenant.

    The caller must authenticate and authorize the tenant before invoking this.
    Do not connect as a superuser, BYPASSRLS role, or migration owner.
    """
    tenant_id = UUID(str(tenant_id))
    with psycopg.connect(database_url) as connection:
        with connection.transaction():
            connection.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))
            yield connection

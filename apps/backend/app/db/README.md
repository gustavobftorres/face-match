# PostgreSQL foundation

Install backend requirements and run `DATABASE_URL=... python -m app.db.migrate` from `apps/backend` with a dedicated migration owner. Migrations run atomically and are tracked in `schema_migrations`. Use a disposable database for integration tests:

```
TEST_DATABASE_ADMIN_URL=... TEST_DATABASE_RUNTIME_URL=... python -m pytest tests/db -q
```

The admin URL must be a superuser in the disposable test database; the runtime URL must be a separate non-superuser role without BYPASSRLS. In deployment, grant the application role only the table privileges it needs, never ownership, BYPASSRLS, superuser, or membership in a privileged role. Migrations and provisioning require a separate privileged path. The application and workers should use `tenant_session(url, authorized_tenant_id)` for every tenant transaction; the helper does not authenticate users or decide authorization. Context is transaction-local and absent context denies tenant rows.

Users are global identities and are not protected by tenant RLS. Future endpoints must limit user data and enforce membership, event and participant authorization; tenant RLS alone does not provide those guarantees. Hostname discovery and tenant provisioning require a separately designed privileged access path; no public resolver is implemented. Existing endpoints and workers do not yet use this layer.

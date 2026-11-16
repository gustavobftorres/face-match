# PostgreSQL foundation

Install backend requirements and run `DATABASE_URL=... python -m app.db.migrate` from `apps/backend` with a dedicated migration owner. Migrations run atomically and are tracked in `schema_migrations`. Use a fresh, empty disposable database for the complete integration suite; the backfill test runs first and the suite is not parallel-safe:

```
TEST_DATABASE_ADMIN_URL=... TEST_DATABASE_RUNTIME_URL=... python -m pytest tests/db -q
```

The admin URL must be a superuser in the disposable test database; the runtime URL must be a separate non-superuser role without BYPASSRLS. In deployment, grant the application role only the table privileges it needs, never ownership, BYPASSRLS, superuser, or membership in a privileged role. Migrations and provisioning require a separate privileged path. The application and workers should use `tenant_session(url, authorized_tenant_id)` for every tenant transaction; the helper does not authenticate users or decide authorization. Context is transaction-local and absent context denies tenant rows.

Users are global identities and are not protected by tenant RLS. Future endpoints must limit user data and enforce membership, event and participant authorization; tenant RLS alone does not provide those guarantees. Tenant provisioning requires a separately controlled privileged access path. Existing endpoints and workers do not yet use this layer.

## Public hostname context rollout

Apply migration 002 with a dedicated migration role that has BYPASSRLS (or is a superuser): its backfill reads `tenant_domains`, which has FORCE RLS, and `row_security = off` deliberately fails rather than silently omit rows. The migration owner owns the private lookup table and SECURITY DEFINER functions. Do not grant runtime role membership in that owner, ownership of these objects, or BYPASSRLS. Existing domains are copied during migration; subsequent changes are synchronized transactionally by a trigger.

After migration, an administrator must provision each existing or new runtime role explicitly, including during rollout:

```
DATABASE_URL=<migration-owner-url> python -m app.db.provision_context <runtime-role>
```

This grants execute on the narrowly scoped lookup function, SELECT on RLS-protected tenants and branding, and schema usage; it revokes direct privileges on the private lookup table from that role. Ensure the role has no indirect grants via PUBLIC or role memberships and cannot create objects in trusted schemas. The command does not remove unrelated existing grants. The endpoint accepts only a validated Host header, ignoring X-Forwarded-Host; the ingress must preserve the validated external Host. Reserved first labels are admin, api, auth and www. Unknown or suspended tenants return 404. The endpoint is public identity/branding only and does not authorize any legacy route.

## Application session and event access

Apply migration 003 and rerun `python -m app.db.provision_context <runtime-role>` with the migration-owner URL. It grants the runtime role access to global users, tenant-scoped sessions and login challenges, and RLS-protected events, memberships and participations. The runtime role must remain non-owner, non-superuser and without BYPASSRLS or privileged inherited roles. Users are global: database access to that table is not tenant isolated; application authorization remains essential.

The new, separate API uses `POST /api/v1/session/challenge` to create a one-use five-minute nonce and host-only secure challenge cookie. The client must obtain a Google ID token with that exact nonce and the configured `GOOGLE_CLIENT_ID` as audience, then send it to `POST /api/v1/session/google` from the same HTTPS origin. The server verifies Google's signature, issuer, audience and expiration and identifies the user by subject, never by email. Both challenge and session records are bound to the canonical hostname, including when one tenant has multiple domains. The eight-hour host-only session is HttpOnly, Secure and SameSite=Strict; only its hash is stored. `GET /api/v1/session` identifies the session, and `DELETE /api/v1/session` requires the `X-CSRF-Token` header matching the `__Host-fm_csrf` cookie and the same HTTPS Origin. It revokes the session server-side. `GET /api/v1/events/{id}` returns a tenant's event to an owner/admin, or a published event to a linked participant; other event IDs return 404. Tenant comes only from Host, not the client body.

This is a backend primitive: there is no frontend login integration, central OAuth callback or cross-subdomain handoff. Google client configuration must permit the chosen login flow and HTTPS origin. Expired challenge/session cleanup, rate limits, session management UI, and policies for closed events remain to be implemented. Existing Drive OAuth, indexing, searches, admin routes and workers remain legacy and are not protected by these new sessions or event checks. Provisioning memberships and participations remains a privileged operation.

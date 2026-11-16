-- Organizer administration: event details, predefined palette + stored logo, and
-- pending owner invitations claimed by a verified Google email at login.
ALTER TABLE public.events
    ADD COLUMN description text CHECK (description IS NULL OR length(description) <= 2000),
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
-- Existing rows were last changed no later than creation, not at migration time.
-- Requires the migration role to bypass FORCE RLS, as migration 002 already does.
UPDATE public.events SET updated_at = created_at;

-- colors holds the resolved palette tokens, palette the predefined key. The logo is
-- a server re-encoded PNG; theme_version is bumped on every change and keys caches.
ALTER TABLE public.tenant_branding
    ADD COLUMN palette text CHECK (palette IS NULL OR palette ~ '^[a-z]{1,32}$'),
    ADD COLUMN logo_png bytea CHECK (logo_png IS NULL OR octet_length(logo_png) <= 524288);

CREATE TABLE public.tenant_invitations (
    tenant_id uuid NOT NULL REFERENCES public.tenants(id),
    email text NOT NULL CHECK (email = lower(email) AND length(email) BETWEEN 3 AND 254),
    role text NOT NULL CHECK (role IN ('owner', 'admin')),
    expires_at timestamptz NOT NULL,
    claimed_by uuid REFERENCES public.users(id),
    claimed_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, email)
);
ALTER TABLE public.tenant_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_invitations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.tenant_invitations
    USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());

-- The runtime role gets no direct access to invitations and no table privilege on
-- memberships. The only membership write it can cause is this function, which turns
-- an unclaimed, unexpired invitation into a membership (or upgrades an existing admin
-- to owner) for the CURRENT tenant context only, when the user's stored email matches.
-- users.email is stored only when Google reports email_verified, and cleared
-- otherwise (see app_session login).
CREATE FUNCTION public.claim_tenant_invitations(p_tenant uuid, p_user uuid) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog SET row_security = off AS $$
DECLARE claimed_count integer;
BEGIN
    IF p_tenant IS NULL OR p_tenant IS DISTINCT FROM public.current_tenant_id() THEN
        RAISE EXCEPTION 'tenant context mismatch' USING ERRCODE = '42501';
    END IF;
    WITH claimed AS (
        UPDATE public.tenant_invitations i
           SET claimed_by = p_user, claimed_at = now()
         WHERE i.tenant_id = p_tenant AND i.claimed_at IS NULL AND i.revoked_at IS NULL AND i.expires_at > now()
           AND i.email = lower((SELECT u.email FROM public.users u WHERE u.id = p_user))
        RETURNING i.tenant_id, i.role
    ), added AS (
        INSERT INTO public.tenant_memberships AS m (tenant_id, user_id, role)
        SELECT tenant_id, p_user, role FROM claimed
        ON CONFLICT (tenant_id, user_id) DO UPDATE SET role = EXCLUDED.role
            WHERE m.role = 'admin' AND EXCLUDED.role = 'owner'
        RETURNING 1
    )
    SELECT count(*) INTO claimed_count FROM claimed;
    RETURN claimed_count;
END $$;

-- Remove grants inherited through ALTER DEFAULT PRIVILEGES, including role grants.
DO $$
DECLARE grantee_name name;
BEGIN
    FOR grantee_name IN
        SELECT r.rolname FROM pg_catalog.pg_class c
        CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) acl
        JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
        WHERE c.oid = 'public.tenant_invitations'::regclass AND acl.grantee <> c.relowner
    LOOP
        EXECUTE pg_catalog.format('REVOKE ALL ON public.tenant_invitations FROM %I', grantee_name);
    END LOOP;
    FOR grantee_name IN
        SELECT r.rolname FROM pg_catalog.pg_proc p
        CROSS JOIN LATERAL pg_catalog.aclexplode(p.proacl) acl
        JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
        WHERE p.oid = 'public.claim_tenant_invitations(uuid, uuid)'::regprocedure AND acl.grantee <> p.proowner
    LOOP
        EXECUTE pg_catalog.format('REVOKE ALL ON FUNCTION public.claim_tenant_invitations(uuid, uuid) FROM %I', grantee_name);
    END LOOP;
END $$;
REVOKE ALL ON public.tenant_invitations FROM PUBLIC;
REVOKE ALL ON FUNCTION public.claim_tenant_invitations(uuid, uuid) FROM PUBLIC;

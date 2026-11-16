CREATE TABLE public.login_challenges (
    tenant_id uuid NOT NULL REFERENCES public.tenants(id),
    hostname text NOT NULL,
    nonce_hash bytea PRIMARY KEY,
    expires_at timestamptz NOT NULL
);
CREATE TABLE public.app_sessions (
    token_hash bytea PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES public.tenants(id),
    hostname text NOT NULL,
    user_id uuid NOT NULL REFERENCES public.users(id),
    csrf_hash bytea NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
ALTER TABLE public.login_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.login_challenges FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.login_challenges USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());
ALTER TABLE public.app_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.app_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON public.app_sessions USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id());

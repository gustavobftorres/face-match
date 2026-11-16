CREATE TABLE public.gallery_jobs (
 id uuid PRIMARY KEY, tenant_id uuid NOT NULL, event_id uuid NOT NULL, requested_by uuid NOT NULL REFERENCES public.users(id),
 folder_id text NOT NULL, status text NOT NULL CHECK (status IN ('queued','processing','ready','failed')),
 created_at timestamptz NOT NULL DEFAULT now(), lease_token uuid, lease_until timestamptz, UNIQUE (tenant_id,event_id,id),
 FOREIGN KEY (tenant_id,event_id) REFERENCES public.events(tenant_id,id)
);
CREATE UNIQUE INDEX gallery_one_active_job ON public.gallery_jobs (tenant_id,event_id) WHERE status IN ('queued','processing');
CREATE TABLE public.gallery_photos (
 id uuid PRIMARY KEY, tenant_id uuid NOT NULL, event_id uuid NOT NULL, source_id text NOT NULL,
 image_bytes bytea NOT NULL, embeddings jsonb NOT NULL, UNIQUE (tenant_id,event_id,id), UNIQUE (tenant_id,event_id,source_id),
 FOREIGN KEY (tenant_id,event_id) REFERENCES public.events(tenant_id,id)
);
CREATE TABLE public.gallery_searches (
 id uuid PRIMARY KEY, tenant_id uuid NOT NULL, event_id uuid NOT NULL, user_id uuid NOT NULL REFERENCES public.users(id),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (tenant_id,event_id,id),
 FOREIGN KEY (tenant_id,event_id) REFERENCES public.events(tenant_id,id)
);
CREATE TABLE public.gallery_results (
 tenant_id uuid NOT NULL, event_id uuid NOT NULL, search_id uuid NOT NULL, photo_id uuid NOT NULL,
 PRIMARY KEY (tenant_id,event_id,search_id,photo_id),
 FOREIGN KEY (tenant_id,event_id,search_id) REFERENCES public.gallery_searches(tenant_id,event_id,id) ON DELETE CASCADE,
 FOREIGN KEY (tenant_id,event_id,photo_id) REFERENCES public.gallery_photos(tenant_id,event_id,id) ON DELETE CASCADE
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['gallery_jobs','gallery_photos','gallery_searches','gallery_results'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY tenant_isolation ON public.%I USING (tenant_id = public.current_tenant_id()) WITH CHECK (tenant_id = public.current_tenant_id())',t);
 END LOOP;
END $$;

-- The migration owner must bypass FORCE RLS. Only a dedicated dispatcher role
-- should be granted EXECUTE; returned identifiers carry no photo data.
CREATE FUNCTION public.gallery_pending_jobs() RETURNS TABLE (tenant_id uuid, event_id uuid, job_id uuid)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog SET row_security = off AS $$
 SELECT j.tenant_id, j.event_id, j.id FROM public.gallery_jobs j
 WHERE (j.status = 'queued' AND j.created_at < now() - interval '30 seconds')
    OR (j.status = 'processing' AND j.lease_until < now())
 ORDER BY j.created_at LIMIT 100
$$;
-- Remove grants inherited through ALTER DEFAULT PRIVILEGES, including role grants.
DO $$
DECLARE grantee_name name;
BEGIN
    FOR grantee_name IN
        SELECT r.rolname FROM pg_catalog.pg_proc p
        CROSS JOIN LATERAL pg_catalog.aclexplode(p.proacl) acl
        JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
        WHERE p.oid = 'public.gallery_pending_jobs()'::regprocedure
          AND acl.grantee <> p.proowner
    LOOP
        EXECUTE pg_catalog.format('REVOKE ALL ON FUNCTION public.gallery_pending_jobs() FROM %I', grantee_name);
    END LOOP;
END $$;
REVOKE ALL ON FUNCTION public.gallery_pending_jobs() FROM PUBLIC;

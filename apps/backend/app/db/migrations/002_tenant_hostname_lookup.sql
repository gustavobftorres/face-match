-- Migration role must bypass RLS to backfill existing domains. The private lookup
-- table is maintained by triggers and is never directly accessible to runtime.
SET LOCAL row_security = off;
CREATE TABLE public.tenant_hostname_lookup (
    hostname text PRIMARY KEY,
    tenant_id uuid NOT NULL
);
-- Default privileges can otherwise expose this private table to existing roles.
DO $$
DECLARE grantee_name name;
BEGIN
    FOR grantee_name IN
        SELECT r.rolname FROM pg_catalog.pg_class c
        CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) acl
        JOIN pg_catalog.pg_roles r ON r.oid = acl.grantee
        WHERE c.oid = 'public.tenant_hostname_lookup'::regclass
          AND acl.grantee <> c.relowner
    LOOP
        EXECUTE pg_catalog.format('REVOKE ALL ON public.tenant_hostname_lookup FROM %I', grantee_name);
    END LOOP;
END $$;
REVOKE ALL ON public.tenant_hostname_lookup FROM PUBLIC;
INSERT INTO public.tenant_hostname_lookup (hostname, tenant_id)
    SELECT hostname, tenant_id FROM public.tenant_domains;

CREATE FUNCTION public.sync_tenant_hostname_lookup() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    IF TG_OP = 'DELETE' OR TG_OP = 'UPDATE' THEN
        DELETE FROM public.tenant_hostname_lookup WHERE hostname = OLD.hostname;
    END IF;
    IF TG_OP = 'INSERT' OR TG_OP = 'UPDATE' THEN
        INSERT INTO public.tenant_hostname_lookup (hostname, tenant_id)
        VALUES (NEW.hostname, NEW.tenant_id);
    END IF;
    RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION public.sync_tenant_hostname_lookup() FROM PUBLIC;
CREATE TRIGGER tenant_hostname_lookup_sync
AFTER INSERT OR UPDATE OR DELETE ON public.tenant_domains
FOR EACH ROW EXECUTE FUNCTION public.sync_tenant_hostname_lookup();

CREATE FUNCTION public.lookup_tenant_hostname(host text) RETURNS uuid
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog AS $$
    SELECT tenant_id FROM public.tenant_hostname_lookup WHERE hostname = host
$$;
REVOKE ALL ON FUNCTION public.lookup_tenant_hostname(text) FROM PUBLIC;

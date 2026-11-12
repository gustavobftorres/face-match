-- Applied by a migration owner; runtime roles must not own these tables or bypass RLS.
CREATE TABLE users (
    id uuid PRIMARY KEY,
    google_subject text NOT NULL UNIQUE CHECK (length(google_subject) > 0),
    email text,
    display_name text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tenants (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE tenant_domains (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    hostname text NOT NULL UNIQUE CHECK (hostname = lower(hostname) AND length(hostname) > 0),
    UNIQUE (tenant_id, id)
);
CREATE TABLE tenant_branding (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(id),
    logo_url text,
    colors jsonb NOT NULL DEFAULT '{}'::jsonb,
    theme_version integer NOT NULL DEFAULT 1 CHECK (theme_version > 0)
);
CREATE TABLE tenant_memberships (
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    user_id uuid NOT NULL REFERENCES users(id),
    role text NOT NULL CHECK (role IN ('owner', 'admin')),
    PRIMARY KEY (tenant_id, user_id)
);
CREATE TABLE events (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    name text NOT NULL,
    slug text NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'closed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, slug)
);
CREATE TABLE event_participations (
    tenant_id uuid NOT NULL,
    event_id uuid NOT NULL,
    user_id uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id, user_id),
    FOREIGN KEY (tenant_id, event_id) REFERENCES events(tenant_id, id)
);

-- Missing/empty context evaluates to NULL and denies access, including writes.
CREATE FUNCTION current_tenant_id() RETURNS uuid LANGUAGE sql STABLE AS $$
    SELECT nullif(current_setting('app.tenant_id', true), '')::uuid
$$;
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenants USING (id = current_tenant_id()) WITH CHECK (id = current_tenant_id());
ALTER TABLE tenant_domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_domains FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant_domains USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
ALTER TABLE tenant_branding ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_branding FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant_branding USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
ALTER TABLE tenant_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_memberships FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant_memberships USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON events USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());
ALTER TABLE event_participations ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_participations FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON event_participations USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id());

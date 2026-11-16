"""Public tenant identity; this does not authorize legacy routes."""
import re

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import settings
from app.db.session import tenant_session
from app.services.branding import logo_token

router = APIRouter()
_LABEL = re.compile(r'^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$')
_RESERVED = frozenset({'admin', 'api', 'auth', 'www'})


def canonical_host(request: Request) -> str:
    # ASGI retains repeated headers; never use proxy-supplied forwarded host.
    hosts = request.headers.getlist('host')
    if len(hosts) != 1:
        raise HTTPException(404, 'Tenant not found')
    raw = hosts[0]
    if raw.count(':') > 1:
        raise HTTPException(404, 'Tenant not found')
    hostname, separator, port = raw.partition(':')
    if separator and (not port.isascii() or not port.isdigit() or len(port) > 5 or not 1 <= int(port) <= 65535):
        raise HTTPException(404, 'Tenant not found')
    host = hostname.lower()
    labels = host.split('.')
    if (not hostname.isascii() or len(host) > 253 or len(labels) < 2
            or any(not _LABEL.fullmatch(label) for label in labels)
            or labels[0] in _RESERVED):
        raise HTTPException(404, 'Tenant not found')
    return host


def tenant_id_for_host(host: str = Depends(canonical_host)):
    # Lookup has access only to a private hostname -> UUID projection.
    with psycopg.connect(settings.DATABASE_URL) as connection:
        row = connection.execute('SELECT public.lookup_tenant_hostname(%s)', (host,)).fetchone()
    tenant_id = row[0] if row else None
    if tenant_id is None:
        raise HTTPException(404, 'Tenant not found')
    return tenant_id


def get_tenant_context(tenant_id=Depends(tenant_id_for_host)):
    with tenant_session(settings.DATABASE_URL, tenant_id) as connection:
        row = connection.execute(
            """SELECT t.name, t.slug,
                      b.logo_png IS NOT NULL, b.logo_url,
                      b.colors, b.theme_version, b.palette
               FROM tenants t LEFT JOIN tenant_branding b ON b.tenant_id = t.id
               WHERE t.id = %s AND t.status = 'active'""", (tenant_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(404, 'Tenant not found')
    name, slug, has_logo, legacy_logo_url, colors, theme_version, palette = row
    logo_url = f'/api/v1/tenant/logo/{logo_token(tenant_id, theme_version)}.png' if has_logo else legacy_logo_url
    return {'name': name, 'slug': slug, 'branding': {
        'logo_url': logo_url, 'colors': colors or {}, 'theme_version': theme_version or 1, 'palette': palette,
    }}


@router.get('/tenant/context')
def tenant_context(context: dict = Depends(get_tenant_context)):
    return context

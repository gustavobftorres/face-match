"""Operator CLI: create a tenant, its hostname, default branding and a pending owner.

Run out-of-band with the migration-owner URL (superuser or BYPASSRLS); it is never
reachable over HTTP and the runtime role cannot do any of this:

    DATABASE_URL=<owner-url> python -m app.db.provision_tenant \
        --name "Aurora Eventos" --slug aurora --hostname aurora.example.com --owner-email owner@example.com

The owner is bound to a Google-verified email, not to a user id: the owner has not
logged in yet, so a pending invitation is stored and claimed at the first login on
this tenant's hostname by a user whose Google account reports that email as verified
(unverified emails are never stored on users). The invitation expires (default 7
days). Re-running with the same values is a no-op;
an existing slug is never taken to mean 'same tenant': adding a hostname or another owner to it
requires --existing-tenant-id <uuid>; when that issues a new invitation, other unclaimed
invitations are revoked (naming someone who is already owner revokes nothing). A run
without it on an existing tenant only verifies (current owner or live invitation) and changes
nothing; reviving an expired, revoked or claimed invitation also requires the flag.
"""
import argparse
import os
import re
import sys
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from app.api.tenant_context import _LABEL, _RESERVED
from app.services.branding import DEFAULT_PALETTE, PALETTES

RESERVED_SLUGS = _RESERVED | {'app', 'static', 'assets', 'cdn', 'mail', 'staging', 'dev', 'test', 'root', 'support', 'status'}
_SLUG = re.compile(r'^[a-z0-9]+(-[a-z0-9]+)*$')
_EMAIL = re.compile(r'^[^@\s,;<>()\[\]\\"]{1,64}@[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\.[a-z]{2,}$')


def validate(name: str, slug: str, hostname: str, owner_email: str) -> tuple[str, str, str, str]:
    name = name.strip()
    if not 1 <= len(name) <= 120:
        raise ValueError('name must be 1-120 characters')
    if not 3 <= len(slug) <= 40 or not _SLUG.fullmatch(slug) or slug in RESERVED_SLUGS:
        raise ValueError('slug must be 3-40 chars of a-z, 0-9 and single hyphens, and not reserved')
    labels = hostname.split('.')
    if (hostname != hostname.lower() or not hostname.isascii() or len(hostname) > 253 or len(labels) < 2
            or any(not _LABEL.fullmatch(label) for label in labels) or labels[0] in RESERVED_SLUGS):
        raise ValueError('hostname must be a lowercase DNS name with at least two labels and a non-reserved first label')
    email = owner_email.strip().lower()
    if len(email) > 254 or not _EMAIL.fullmatch(email):
        raise ValueError('owner email is invalid')
    return name, slug, hostname, email


def provision(database_url: str, name: str, slug: str, hostname: str, owner_email: str, invitation_days: int = 7,
              existing_tenant_id: str | None = None) -> dict:
    """Create a tenant, or re-run exactly what was provisioned.

    An existing slug is never inferred to be "the same tenant": unless the hostname is
    already bound to it and the owner email already holds (or was invited to) ownership,
    the call fails. Adding a hostname or another owner to an existing tenant requires
    passing that tenant's id explicitly (--existing-tenant-id); when a new invitation is
    issued, other pending invitations are revoked so only the newly named owner can claim.
    Naming an email that is already an owner issues nothing and revokes nothing.
    """
    name, slug, hostname, owner_email = validate(name, slug, hostname, owner_email)
    if not 1 <= invitation_days <= 30:
        raise ValueError('invitation days must be between 1 and 30')
    if existing_tenant_id is not None:
        try:
            existing_tenant_id = str(UUID(existing_tenant_id))
        except ValueError:
            raise ValueError('existing tenant id must be a UUID')
    with psycopg.connect(database_url) as conn:
        with conn.transaction():
            flags = conn.execute('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user').fetchone()
            if not flags or not flags[0]:
                raise ValueError('provisioning requires the migration-owner role (superuser or BYPASSRLS)')
            conn.execute('SELECT pg_advisory_xact_lock(759346183)')
            created = conn.execute('INSERT INTO tenants (id, name, slug) VALUES (%s, %s, %s) ON CONFLICT (slug) DO NOTHING', (uuid4(), name, slug)).rowcount == 1
            tenant_id, status = conn.execute('SELECT id, status FROM tenants WHERE slug = %s', (slug,)).fetchone()
            tenant_id_text = str(tenant_id)
            if status != 'active':
                raise ValueError('tenant is suspended; refusing to provision it')
            domain = conn.execute('SELECT tenant_id FROM tenant_domains WHERE hostname = %s', (hostname,)).fetchone()
            if domain and domain[0] != tenant_id:
                raise ValueError('hostname already belongs to another tenant')
            confirmed = existing_tenant_id is not None
            if not created:
                if confirmed and existing_tenant_id != tenant_id_text:
                    raise ValueError('existing tenant id does not match the tenant with this slug')
                if not confirmed:
                    # Flagless re-run of an existing tenant is verification only: it must match
                    # a current owner or a live invitation, and it changes nothing.
                    live = domain and conn.execute("""SELECT 1 FROM tenant_invitations i WHERE i.tenant_id = %s AND i.email = %s
                            AND i.claimed_at IS NULL AND i.revoked_at IS NULL AND i.expires_at > now()
                        UNION ALL SELECT 1 FROM tenant_memberships m JOIN users u ON u.id = m.user_id
                            WHERE m.tenant_id = %s AND m.role = 'owner' AND lower(u.email) = %s""",
                                                   (tenant_id, owner_email, tenant_id, owner_email)).fetchone()
                    if not live:
                        raise ValueError('slug already exists; this would add a hostname or owner, or revive an expired, revoked or '
                                         'claimed invitation. Re-run with --existing-tenant-id <uuid> if that is intended')
                    return {'created': False, 'tenant_id': tenant_id_text, 'slug': slug, 'hostname': hostname, 'status': status, 'owner_invited': False}
            if not domain:
                conn.execute('INSERT INTO tenant_domains (id, tenant_id, hostname) VALUES (%s, %s, %s)', (uuid4(), tenant_id, hostname))
            conn.execute('INSERT INTO tenant_branding (tenant_id, palette, colors) VALUES (%s, %s, %s) ON CONFLICT (tenant_id) DO NOTHING',
                         (tenant_id, DEFAULT_PALETTE, Jsonb(PALETTES[DEFAULT_PALETTE])))
            already_owner = conn.execute("""SELECT 1 FROM tenant_memberships m JOIN users u ON u.id = m.user_id
                WHERE m.tenant_id = %s AND m.role = 'owner' AND lower(u.email) = %s""", (tenant_id, owner_email)).fetchone()
            invited = False
            if not already_owner:
                # Only the named owner may claim: revoke every other unclaimed invitation.
                conn.execute("UPDATE tenant_invitations SET revoked_at = now() WHERE tenant_id = %s AND email <> %s AND claimed_at IS NULL AND revoked_at IS NULL",
                             (tenant_id, owner_email))
                conn.execute("""INSERT INTO tenant_invitations (tenant_id, email, role, expires_at)
                    VALUES (%s, %s, 'owner', now() + make_interval(days => %s))
                    ON CONFLICT (tenant_id, email) DO UPDATE SET expires_at = EXCLUDED.expires_at, claimed_at = NULL, claimed_by = NULL, revoked_at = NULL""",
                             (tenant_id, owner_email, invitation_days))
                invited = True
    return {'created': created, 'tenant_id': tenant_id_text, 'slug': slug, 'hostname': hostname, 'status': status, 'owner_invited': invited}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--name', required=True)
    parser.add_argument('--slug', required=True)
    parser.add_argument('--hostname', required=True)
    parser.add_argument('--owner-email', required=True)
    parser.add_argument('--invitation-days', type=int, default=7)
    parser.add_argument('--existing-tenant-id', help='explicitly allow adding a hostname or owner to this existing tenant')
    args = parser.parse_args(argv)
    try:
        result = provision(os.environ['DATABASE_URL'], args.name, args.slug, args.hostname, args.owner_email, args.invitation_days, args.existing_tenant_id)
    except (ValueError, KeyError) as error:
        print(f'error: {error if isinstance(error, ValueError) else "DATABASE_URL is required"}', file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == '__main__':
    sys.exit(main())

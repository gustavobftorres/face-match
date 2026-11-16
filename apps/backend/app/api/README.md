# API Module

## Responsibilities
This module handles HTTP requests and WebSocket connections.

## Files
- `auth.py`:
    - `GET /auth/google/url`: Returns a Google OAuth authorization URL.
    - `POST /auth/google/callback`: Exchanges an authorization code for an access token and user email.
- `endpoints.py`:
    - `GET /folders`: Lists indexed Google Drive albums and statuses.
    - `GET /folders/{folder_id}`: Returns metadata and status for a single indexed album.
    - `POST /folders/index`: Queues background face-embedding indexing for a private (OAuth) or public Google Drive folder.
    - `POST /folders/{folder_id}/search`: Searches precomputed embeddings in `EmbeddingStore` using threadpool face encoding and triggers background thumbnail pre-warming.
    - `GET /drive/image/{file_id}`: Serves cached `thumb`/`preview` JPEGs or streams full Drive images (`?size=thumb|preview|full&download=true|false`) with immutable cache headers.
    - `POST /scan`: Accepts a drive link, base64 target face, and OAuth `access_token`. Initiates the scanning process.
    - `WS /ws/updates/{scan_id}`: WebSocket endpoint that pushes real-time progress updates.

## Endpoints
- **GET /api/v1/auth/google/url** → `{ "url": "..." }`
- **POST /api/v1/auth/google/callback** → `{ "access_token": "...", "email": "..." }`
- **GET /api/v1/folders** → `[{ "id": "...", "name": "...", ... }]`
- **GET /api/v1/folders/{folder_id}** → `{ "id": "...", "status": "...", ... }`
- **POST /api/v1/folders/index** → `{ "folder_id": "...", "total_files": N }`
- **POST /api/v1/folders/{folder_id}/search** → `{ "folder_id": "...", "matches": [...] }`
- **GET /api/v1/drive/image/{file_id}** → image byte stream
- **POST /api/v1/scan** → `{ "message": "Scan started", "total_files": N }`
- **WebSocket /api/v1/ws/updates/{scan_id}** → real-time events

## Organizer administration (`tenant_admin.py`)

Tenant admin routes under `/api/v1/admin` require a session cookie of an owner/admin of the host's tenant; mutations also require Origin and `X-CSRF-Token`. They are separate from the legacy `/admin` frontend page and the Drive endpoints above.
- `GET /admin/access` -> `{role}`; `GET/POST /admin/events`, `GET/PATCH /admin/events/{id}`, `POST /admin/events/{id}/publish|unpublish|close`.
- `GET/PUT /admin/branding` (`{palette}` from predefined palettes), `PUT/DELETE /admin/branding/logo` (multipart `logo`; PNG/JPEG/WebP up to 1 MiB, decoded and re-encoded to a bounded PNG).
- `GET /tenant/logo/{token}.png` (public, tenant by hostname only): `image/png`, `nosniff`; the token is opaque tenant+version, only the current one is served (immutable, ETag/304), else 404 `no-store`. `GET /tenant/context` also returns `branding.palette`.
- There is no HTTP route to create tenants; use `python -m app.db.provision_tenant` (see `app/db/README.md`).

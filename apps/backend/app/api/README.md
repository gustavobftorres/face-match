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

# API Module

## Responsibilities
This module handles HTTP requests and WebSocket connections.

## Files
- `auth.py`:
    - `GET /auth/google/url`: Returns a Google OAuth authorization URL.
    - `POST /auth/google/callback`: Exchanges an authorization code for an access token and user email.
- `endpoints.py`:
    - `POST /scan`: Accepts a drive link, base64 target face, and OAuth `access_token`. Initiates the scanning process.
    - `WS /ws/updates`: WebSocket endpoint that pushes real-time progress updates.

## Endpoints
- **GET /api/v1/auth/google/url** → `{ "url": "..." }`
- **POST /api/v1/auth/google/callback** → `{ "access_token": "...", "email": "..." }`
- **POST /api/v1/scan** → `{ "message": "Scan started", "total_files": N }`
- **WebSocket /api/v1/ws/updates** → real-time events

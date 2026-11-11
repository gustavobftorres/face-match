# face-match

Search for your face across photos in a Google Drive folder using AI face recognition.

## Structure

```
face-match/
├── apps/
│   ├── backend/   # FastAPI + Celery + Redis (Python)
│   └── frontend/  # Next.js (TypeScript)
└── Makefile
```

## Requirements

- Python 3.13+ (via pyenv recommended)
- Node.js 18+
- [Homebrew](https://brew.sh) (macOS) — used to install Redis and cmake
- A Google Cloud project with OAuth 2.0 credentials and the Google Drive API enabled

## Setup

### 1. Google OAuth credentials

Create `apps/backend/.env.local`:

```env
GOOGLE_CLIENT_ID=your_client_id
GOOGLE_CLIENT_SECRET=your_client_secret
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/callback
```

Create `apps/frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000/api/v1/ws/updates
```

The WebSocket value is the base URL. The client appends `/{scan_id}` and, when
reconnecting, `?after_sequence=<last_seen_sequence>`.

### 2. Install dependencies

```bash
# Install cmake (required to compile dlib on macOS)
brew install cmake dlib

make install
```

### 3. Run locally

```bash
make dev
```

- Frontend → http://localhost:3000
- Backend  → http://localhost:8000

### 4. Stop all services

```bash
make stop
```

## How it works

1. Log in with Google to grant Drive read access
2. Paste a Google Drive folder link
3. Upload a reference photo of your face
4. The backend scans every photo in the folder using `face_recognition`
5. Scan-scoped, sequenced events stream back in real time via WebSocket and can
   be replayed after a reconnect

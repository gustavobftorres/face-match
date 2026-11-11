# Face Recon Drive Backend - API Documentation

## Base URL

| Protocol  | URL                                  |
|-----------|--------------------------------------|
| HTTP      | `http://localhost:8000/api/v1`       |
| WebSocket | `ws://localhost:8000/api/v1`         |

---

## Authentication Flow (Google OAuth)

### 1. Get Authorization URL

**`GET /auth/google/url`**

**Response `200 OK`:**
```json
{
  "url": "https://accounts.google.com/o/oauth2/auth?...",
  "code_verifier": "<pkce_code_verifier>"
}
```

Store `code_verifier` temporarily, then redirect the user to `url` to initiate
the OAuth consent screen.

---

### 2. Exchange Code for Token

**`POST /auth/google/callback`**

**Request Body:**
```json
{
  "code": "<authorization_code_from_google>",
  "code_verifier": "<pkce_code_verifier_from_step_1>"
}
```

**Response `200 OK`:**
```json
{
  "access_token": "<google_access_token>",
  "email": "user@gmail.com"
}
```

**Errors:** `400` — OAuth exchange failed or invalid code.

---

## 3. Start Scan

**`POST /scan`**

**Request Body:**
```json
{
  "drive_link": "https://drive.google.com/drive/folders/YOUR_FOLDER_ID",
  "target_face": "<base64_encoded_image>",
  "access_token": "<google_oauth_token_from_step_2>"
}
```

**Response `200 OK`:**
```json
{
  "message": "Scan started",
  "total_files": 150,
  "scan_id": "8040c4e5-02b0-44d3-9b5c-499e3a3dc4df"
}
```

> Use `scan_id` to open the scan-specific WebSocket and poll its status.

**Errors:**

| Status | Reason                                       |
|--------|----------------------------------------------|
| `400`  | Invalid Base64 string or no face detected    |
| `401`  | Google token expired or invalid              |
| `404`  | No images found in the Drive folder          |
| `500`  | Unexpected server error                      |

---

## 4. Real-time Updates (WebSocket)

**`WS /ws/updates/{scan_id}?after_sequence=0`**

Connect immediately after calling `/scan`. Each socket subscribes only to the
requested scan. Every event contains that `scan_id` and a monotonically
increasing `sequence` number.

On first connection, omit `after_sequence` or use `0`. On reconnect, pass the
last sequence processed by the client. The server first replays persisted events
whose `sequence` is greater than `after_sequence`, then continues with live
events from the same scan. Clients should retain the greatest processed sequence
and ignore duplicate or older events defensively.

### Event Types

#### `started`
Emitted once when a scan begins.
```json
{
  "type": "started",
  "scan_id": "...",
  "sequence": 1,
  "total_files": 150
}
```

#### `progress`
Emitted for each processed file that is either not a match or has no face.
```json
{
  "type": "progress",
  "scan_id": "...",
  "sequence": 2,
  "file_id": "...",
  "file_name": "photo.jpg",
  "status": "no_match" | "no_face_found"
}
```

#### `match`
Emitted when the target face is found in an image.
```json
{
  "type": "match",
  "scan_id": "...",
  "sequence": 3,
  "file_id": "...",
  "file_name": "photo.jpg",
  "status": "match",
  "download_url": "https://drive.google.com/uc?id=...&export=download"
}
```

#### `completed`
Emitted once when all files in the scan have been processed (including errored/timed-out files).
```json
{
  "type": "completed",
  "scan_id": "...",
  "sequence": 151
}
```

#### `error`
Emitted when a single file fails to process (download error, decoding failure, etc.). The scan continues for other files.
```json
{
  "type": "error",
  "scan_id": "...",
  "sequence": 4,
  "file_id": "...",
  "file_name": "photo.jpg",
  "error": "Download timed out after retries"
}
```

A coordination failure that terminates the entire scan uses the same event type
with a terminal status and no file fields:

```json
{
  "type": "error",
  "scan_id": "...",
  "sequence": 5,
  "status": "failed",
  "error": "Scan state expired before a file could be processed"
}
```

#### `token_expired`
Emitted once when the Google access token expires mid-scan. That scan enters the
terminal `token_expired` state, so its later tasks do not publish normal results.
The user must re-authenticate and start a new scan.
```json
{
  "type": "token_expired",
  "scan_id": "...",
  "sequence": 6,
  "message": "Google token expired. Please re-authenticate and restart the scan."
}
```

---

## 5. Scan Status (Polling Fallback)

**`GET /scan/{scan_id}/status`**

Use this as a fallback if the WebSocket connection drops. `last_sequence` is the
latest event cursor known by Redis; use it to track progress and reconnect the
WebSocket with `after_sequence`. Scan state and event history have a one-hour
TTL.

**Response `200 OK` examples:**
```json
{ "scan_id": "...", "status": "running",       "remaining": 42, "last_sequence": 17 }
{ "scan_id": "...", "status": "completed",     "remaining": 0,  "last_sequence": 151 }
{ "scan_id": "...", "status": "token_expired", "remaining": 0,  "last_sequence": 23 }
{ "scan_id": "...", "status": "failed",        "remaining": 0,  "last_sequence": 8 }
{ "scan_id": "...", "status": "unknown",                        "last_sequence": 0 }
```

The possible states are `running`, `completed`, `token_expired`, `failed`, and
`unknown`. `unknown` means no active or retained state exists for that scan ID.

---

## Notes

- **Retry behavior:** All network-level errors (timeouts, SSL EOF, connection resets) are retried up to **3 times** with exponential backoff. Permanent failures emit an `error` event.
- **SSL/Transport errors:** `[SSL: UNEXPECTED_EOF_WHILE_READING]`, connection resets, and dropped connections during download are all retried automatically.
- **Face matching:** The production distance threshold is currently `0.6`; a
  face matches when its distance is strictly less than that value. Images are
  resized to at most `1000 px` on their longest side before encoding.
- **Large scans:** Worker process is recycled every 50 tasks to prevent memory growth. Only 1 task is prefetched at a time.
- **Task limits:** The Celery soft time limit is `360 s`; the hard limit is
  `420 s`.
- **Redis isolation:** Counters, status, processed-file sets, event history,
  sequence counters, and pub/sub channels are scoped by `scan_id`. Terminal
  states are `completed`, `token_expired`, and `failed`.
- **WebSocket reconnect:** Poll `GET /scan/{scan_id}/status`, retain its
  `last_sequence`, and reconnect to
  `/ws/updates/{scan_id}?after_sequence=<last_processed_sequence>`.

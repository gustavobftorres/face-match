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
{ "url": "https://accounts.google.com/o/oauth2/auth?..." }
```

Redirect the user to this URL to initiate the OAuth consent screen.

---

### 2. Exchange Code for Token

**`POST /auth/google/callback`**

**Request Body:**
```json
{ "code": "<authorization_code_from_google>" }
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

> Use `scan_id` to correlate WebSocket events to a specific scan session.

**Errors:**

| Status | Reason                                       |
|--------|----------------------------------------------|
| `400`  | Invalid Base64 string or no face detected    |
| `401`  | Google token expired or invalid              |
| `404`  | No images found in the Drive folder          |
| `500`  | Unexpected server error                      |

---

## 4. Real-time Updates (WebSocket)

**`WS /ws/updates`**

Connect immediately after calling `/scan`. All events from all active scans are broadcast on this channel. Use `scan_id` to filter events relevant to your session.

### Event Types

#### `started`
Emitted once when a scan begins.
```json
{
  "type": "started",
  "scan_id": "...",
  "total_files": 150
}
```

#### `progress`
Emitted for each processed file that is either not a match or has no face.
```json
{
  "type": "progress",
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
  "scan_id": "..."
}
```

#### `error`
Emitted when a single file fails to process (download error, decoding failure, etc.). The scan continues for other files.
```json
{
  "type": "error",
  "file_id": "...",
  "file_name": "photo.jpg",
  "error": "Download timed out after retries"
}
```

#### `token_expired`
Emitted when the Google access token expires mid-scan. All remaining tasks are purged. The user must re-authenticate.
```json
{
  "type": "token_expired",
  "message": "Google token expired. Please re-authenticate and restart the scan."
}
```

---

## 5. Scan Status (Polling Fallback)

**`GET /scan/{scan_id}/status`**

Use this as a fallback if the WebSocket connection drops before the `completed` event is received. The status is persisted in Redis for 1 hour after a scan finishes.

**Response `200 OK`:**
```json
{ "scan_id": "...", "status": "completed", "remaining": 0 }
{ "scan_id": "...", "status": "running",   "remaining": 42 }
{ "scan_id": "...", "status": "unknown" }
```

---

## Notes

- **Retry behavior:** All network-level errors (timeouts, SSL EOF, connection resets) are retried up to **3 times** with exponential backoff. Permanent failures emit an `error` event.
- **SSL/Transport errors:** `[SSL: UNEXPECTED_EOF_WHILE_READING]`, connection resets, and dropped connections during download are all retried automatically.
- **Face matching:** Distance threshold of `0.45` (stricter than the library default `0.6`) to minimize false positives.
- **Large scans:** Worker process is recycled every 50 tasks to prevent memory growth. Only 1 task is prefetched at a time.
- **WebSocket reconnect:** If the WebSocket disconnects mid-scan, poll `GET /scan/{scan_id}/status` to check if the scan completed.

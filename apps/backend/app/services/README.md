# services

Business logic for interacting with Google Drive and running face recognition.

## Files

### `drive_service.py`
Authenticates with Google Drive using an OAuth access token, paginates through a folder, and returns a list of image file metadata.

### `ai_service.py`
Handles image decoding and face recognition.

**`get_face_encodings(image_content: bytes) -> list`**
- Decodes image bytes with PIL.
- Converts to RGB.
- Resizes to max `1000 px` on the longest side to reduce memory and CPU usage.
- Returns face encodings using `face_recognition` defaults.

**`compare_faces(known_encoding, unknown_encoding) -> bool`**
- Computes the Euclidean distance between two 128-d face vectors.
- Returns `True` only if `distance < 0.6`.
- `0.6` is the current production threshold. Offline evaluation may calibrate
  separate thresholds for experiments; it does not change this constant.

## Constants

| Constant                       | Value  | Purpose                               |
|-------------------------------|--------|---------------------------------------|
| `MAX_IMAGE_DIMENSION`          | `1000` | Max px before resizing                |
| `FACE_MATCH_DISTANCE_THRESHOLD`| `0.6`  | Exclusive max distance for a match    |

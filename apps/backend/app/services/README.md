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
- Resizes to max `1200 px` on the longest side to reduce memory and CPU usage.
- Returns face encodings using `face_recognition` with `model="small"` for maximum speed.

**`compare_faces(known_encoding, unknown_encoding) -> bool`**
- Computes the Euclidean distance between two 128-d face vectors.
- Returns `True` only if `distance < 0.45`.
- Threshold of `0.45` is intentionally stricter than the library default (`0.6`) to minimize false positives.

## Constants

| Constant                       | Value  | Purpose                               |
|-------------------------------|--------|---------------------------------------|
| `MAX_IMAGE_DIMENSION`          | `1200` | Max px before resizing                |
| `FACE_MATCH_DISTANCE_THRESHOLD`| `0.45` | Max face distance to count as a match |

# Schemas Module

## Responsibilities
This module defines Pydantic models for data validation and serialization.

## Files
- `requests.py`: Contains request and response models including `ScanRequest`, `FolderIndexRequest` (with optional `access_token` for public Drive folders), `PublicSearchRequest`, `PublicSearchResponse`, `SearchMatchResponse`, and `FolderResponse`.
- `auth.py`: OAuth callback and token response schemas.

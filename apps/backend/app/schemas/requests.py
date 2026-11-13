from pydantic import BaseModel
from typing import Optional, List

class ScanRequest(BaseModel):
    drive_link: str
    target_face: str
    access_token: str

class FolderIndexRequest(BaseModel):
    drive_link: str
    access_token: Optional[str] = None

class PublicSearchRequest(BaseModel):
    target_face: str
    tolerance: float = 0.6

class SearchMatchResponse(BaseModel):
    file_id: str
    file_name: str
    confidence: float
    download_url: Optional[str] = None
    thumbnail_url: Optional[str] = None

class PublicSearchResponse(BaseModel):
    folder_id: str
    total_photos: int
    matches: List[SearchMatchResponse]
    elapsed_ms: int

class FolderResponse(BaseModel):
    id: str
    name: str
    drive_folder_id: str
    photo_count: int
    faces_count: int
    status: str
    indexed_at: str

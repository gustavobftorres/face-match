from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Face Recon Drive"
    REDIS_URL: str = "redis://localhost:6379/0"
    ALLOWED_ORIGINS: list[str] = ["*"]
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/auth/callback"
    DATABASE_URL: str = ""
    DATABASE_URL_UNPOOLED: str = ""
    FACE_MATCH_DB_PATH: str = str(BACKEND_ROOT / "face_match_embeddings.db")
    THUMBNAIL_CACHE_DIR: str = str(BACKEND_ROOT / ".cache" / "thumbnails")
    PREWARM_THUMBNAILS_ON_SEARCH: bool = True
    DRIVE_EMBEDDED_FOLDER_URL: str = "https://drive.google.com/embeddedfolderview?id={folder_id}"
    DRIVE_PUBLIC_FILE_VIEW_URL: str = "https://drive.google.com/file/d/{file_id}/view"
    DRIVE_PUBLIC_DOWNLOAD_URL: str = "https://drive.usercontent.google.com/download?id={file_id}&export=download"
    DRIVE_PUBLIC_UC_DOWNLOAD_URL: str = "https://drive.google.com/uc?id={file_id}&export=download"
    DRIVE_PUBLIC_THUMBNAIL_URL: str = "https://drive.google.com/thumbnail?id={file_id}&sz=w800"
    DRIVE_FAST_THUMBNAIL_URL: str = "https://lh3.googleusercontent.com/d/{file_id}=w{width}"
    DRIVE_THUMBNAIL_SIZE_URL: str = "https://drive.google.com/thumbnail?id={file_id}&sz=w{width}"
    DRIVE_API_FILE_MEDIA_URL: str = "https://www.googleapis.com/drive/v3/files/{file_id}?alt=media"

    model_config = SettingsConfigDict(
        env_file=(
            str(REPO_ROOT / ".env"),
            str(REPO_ROOT / ".env.local"),
            str(BACKEND_ROOT / ".env"),
            str(BACKEND_ROOT / ".env.local"),
            ".env",
            ".env.local",
        ),
        case_sensitive=True,
        extra="ignore",
    )

settings = Settings()
for _env_attr in ("REDIS_URL", "DATABASE_URL", "DATABASE_URL_UNPOOLED"):
    _env_val = getattr(settings, _env_attr, "")
    if isinstance(_env_val, str):
        setattr(settings, _env_attr, _env_val.strip("'\" \n"))

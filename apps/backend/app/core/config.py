from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Face Recon Drive"
    REDIS_URL: str = "redis://localhost:6379/0"
    ALLOWED_ORIGINS: list[str] = ["*"]
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:3000/auth/callback"

    class Config:
        env_file = (".env", ".env.local")
        case_sensitive = True
        extra = "ignore"

settings = Settings()
if isinstance(settings.REDIS_URL, str):
    settings.REDIS_URL = settings.REDIS_URL.strip("'\" \n")

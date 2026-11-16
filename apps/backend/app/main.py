from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.endpoints import router as api_router
from app.api.auth import router as auth_router
from app.api.tenant_context import router as tenant_context_router
from app.api.app_session import router as app_session_router
from app.api.event_gallery import router as event_gallery_router
from app.api.tenant_admin import router as tenant_admin_router, public_router as tenant_logo_router
from app.api.gallery_limit import GalleryUploadLimit, LogoUploadLimit
from app.services.image_cache_service import image_cache_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await image_cache_service.close()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(GalleryUploadLimit)
app.add_middleware(LogoUploadLimit)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)
app.include_router(auth_router, prefix=f"{settings.API_V1_STR}/auth")

app.include_router(tenant_context_router, prefix=settings.API_V1_STR)

app.include_router(app_session_router, prefix=settings.API_V1_STR)

app.include_router(event_gallery_router, prefix=settings.API_V1_STR)

app.include_router(tenant_admin_router, prefix=settings.API_V1_STR)

app.include_router(tenant_logo_router, prefix=settings.API_V1_STR)

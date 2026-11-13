import asyncio
import logging
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

import httpx
from PIL import Image, ImageOps

from app.core.config import settings

logger = logging.getLogger(__name__)

IMAGE_VARIANT_WIDTHS: Dict[str, int] = {
    "thumb": 480,
    "preview": 1080,
}

IMAGE_CACHE_HEADERS: Dict[str, str] = {
    "Cache-Control": "public, max-age=604800, immutable",
}


class ImageCacheService:
    def __init__(self, cache_dir: str = settings.THUMBNAIL_CACHE_DIR):
        self.cache_dir = Path(cache_dir)
        self._client: Optional[httpx.AsyncClient] = None
        self._locks: Dict[tuple[str, str], asyncio.Lock] = {}

    def get_cache_path(self, file_id: str, variant: str) -> Path:
        return self.cache_dir / variant / f"{file_id}.jpg"

    def get_http_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=20.0,
                limits=httpx.Limits(max_connections=40, max_keepalive_connections=20),
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    @staticmethod
    def resize_to_jpeg(raw_bytes: bytes, max_width: int, quality: int = 82) -> bytes:
        image = Image.open(BytesIO(raw_bytes))
        image = ImageOps.exif_transpose(image)
        if image.mode != "RGB":
            image = image.convert("RGB")
        if max(image.size) > max_width:
            image.thumbnail((max_width, max_width), Image.LANCZOS)
        output = BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True, progressive=True)
        return output.getvalue()

    def save_variant_bytes(self, file_id: str, variant: str, data: bytes) -> Path:
        target = self.get_cache_path(file_id, variant)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.parent / f".{file_id}.{uuid.uuid4().hex}.tmp"
        tmp_path.write_bytes(data)
        os.replace(tmp_path, target)
        return target

    def cache_thumbnail_from_bytes(
        self, file_id: str, raw_bytes: bytes, variant: str = "thumb"
    ) -> Optional[Path]:
        max_width = IMAGE_VARIANT_WIDTHS.get(variant)
        if max_width is None or not raw_bytes:
            return None
        try:
            resized = self.resize_to_jpeg(raw_bytes, max_width=max_width)
            return self.save_variant_bytes(file_id, variant, resized)
        except Exception as exc:
            logger.warning(f"Failed to cache {variant} for {file_id}: {exc}")
            return None

    async def _fetch_candidate_image(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[tuple[bytes, str]]:
        client = self.get_http_client()
        try:
            response = await client.get(url, headers=headers)
        except Exception:
            return None
        content_type = response.headers.get("content-type", "").lower()
        if response.status_code != 200 or not content_type.startswith("image/"):
            return None
        if not response.content:
            return None
        return response.content, content_type

    async def _fetch_variant_bytes(
        self,
        file_id: str,
        variant: str,
        access_token: Optional[str] = None,
    ) -> Optional[bytes]:
        width = IMAGE_VARIANT_WIDTHS[variant]
        if access_token:
            api_url = settings.DRIVE_API_FILE_MEDIA_URL.format(file_id=file_id)
            fetched = await self._fetch_candidate_image(
                api_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if fetched is not None:
                raw_bytes, _ = fetched
                return await asyncio.to_thread(self.resize_to_jpeg, raw_bytes, width)

        thumbnail_candidates = (
            settings.DRIVE_FAST_THUMBNAIL_URL.format(file_id=file_id, width=width),
            settings.DRIVE_THUMBNAIL_SIZE_URL.format(file_id=file_id, width=width),
        )
        for url in thumbnail_candidates:
            fetched = await self._fetch_candidate_image(url)
            if fetched is not None:
                raw_bytes, content_type = fetched
                if "jpeg" in content_type or "jpg" in content_type:
                    return raw_bytes
                return await asyncio.to_thread(self.resize_to_jpeg, raw_bytes, width)

        fallback_url = settings.DRIVE_PUBLIC_DOWNLOAD_URL.format(file_id=file_id)
        fetched = await self._fetch_candidate_image(fallback_url)
        if fetched is not None:
            raw_bytes, _ = fetched
            return await asyncio.to_thread(self.resize_to_jpeg, raw_bytes, width)
        return None

    async def get_or_fetch_variant(
        self,
        file_id: str,
        variant: str,
        access_token: Optional[str] = None,
    ) -> Optional[Path]:
        if variant not in IMAGE_VARIANT_WIDTHS:
            return None
        cache_path = self.get_cache_path(file_id, variant)
        if cache_path.is_file() and cache_path.stat().st_size > 0:
            return cache_path

        lock_key = (file_id, variant)
        lock = self._locks.setdefault(lock_key, asyncio.Lock())
        async with lock:
            if cache_path.is_file() and cache_path.stat().st_size > 0:
                return cache_path
            variant_bytes = await self._fetch_variant_bytes(
                file_id=file_id,
                variant=variant,
                access_token=access_token,
            )
            if not variant_bytes:
                return None
            saved_path = self.save_variant_bytes(file_id, variant, variant_bytes)

        if len(self._locks) > 4096:
            stale = [k for k, v in self._locks.items() if not v.locked()]
            for key in stale[:2048]:
                self._locks.pop(key, None)

        return saved_path

    async def prewarm_variants(
        self,
        file_ids: Iterable[str],
        token_resolver: Callable[[str], Optional[str]],
        variant: str = "thumb",
        concurrency: int = 8,
    ) -> None:
        if variant not in IMAGE_VARIANT_WIDTHS:
            return
        pending = [
            fid
            for fid in dict.fromkeys(file_ids)
            if not (self.get_cache_path(fid, variant).is_file())
        ]
        if not pending:
            return

        semaphore = asyncio.Semaphore(concurrency)

        async def warm_one(fid: str) -> None:
            async with semaphore:
                token = token_resolver(fid)
                await self.get_or_fetch_variant(fid, variant, access_token=token)

        await asyncio.gather(*(warm_one(fid) for fid in pending), return_exceptions=True)


image_cache_service = ImageCacheService()

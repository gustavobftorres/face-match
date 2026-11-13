from html import unescape
import re
from typing import Dict, List, Optional, Tuple
import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from app.core.config import settings

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".heic")
NON_IMAGE_EXTENSIONS = (".pdf", ".txt", ".csv", ".zip", ".rar", ".mp4", ".mov", ".avi", ".doc", ".docx", ".xls", ".xlsx")


def get_drive_service(access_token: str):
    creds = Credentials(token=access_token)
    return build("drive", "v3", credentials=creds)


def extract_folder_id(url: str) -> str:
    candidate = (url or "").strip()
    match = re.search(r"folders/([a-zA-Z0-9_-]+)", candidate)
    if match:
        return match.group(1)
    match = re.search(r"(?:^|[?&])id=([a-zA-Z0-9_-]+)", candidate)
    if match:
        return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{10,}", candidate):
        return candidate
    raise ValueError(f"Could not extract a valid Google Drive folder ID from the provided link: {url!r}")


def _is_image_entry(block: str, name: str) -> bool:
    if "/drive/folders/" in block or "type/application/vnd.google-apps.folder" in block:
        return False
    if "type/image/" in block:
        return True
    lowered = name.lower().strip()
    if lowered.endswith(IMAGE_EXTENSIONS):
        return True
    if lowered.endswith(NON_IMAGE_EXTENSIONS):
        return False
    return "application/vnd.google-apps.shortcut" in block


def _resolve_public_shortcut(file_id: str) -> str:
    view_url = settings.DRIVE_PUBLIC_FILE_VIEW_URL.format(file_id=file_id)
    with httpx.Client(follow_redirects=True, timeout=15.0) as client:
        response = client.get(view_url)
    match = re.search(r"/file/d/([A-Za-z0-9_-]+)", str(response.url))
    return match.group(1) if match else file_id


def parse_public_embedded_folder(html: str, default_name: str = "Drive Album") -> Tuple[str, List[Dict[str, str]]]:
    if 'class="flip-entries"' not in html:
        raise PermissionError("Google Drive folder is private or embedded listing is unavailable")

    title_match = re.search(r"<title>(.*?)</title>", html, re.S)
    folder_name = default_name
    if title_match:
        raw_title = unescape(title_match.group(1)).strip()
        cleaned_title = re.sub(r"\s*-\s*Google Drive\s*$", "", raw_title).strip()
        if cleaned_title:
            folder_name = cleaned_title

    blocks = re.split(r'<div\b(?=[^>]*\bclass="flip-entry"(?:\s|>))', html)[1:]
    files: List[Dict[str, str]] = []
    seen_ids = set()

    for block in blocks:
        identity = re.search(r'id="entry-([A-Za-z0-9_-]+)"', block)
        name_match = re.search(r'<div class="flip-entry-title">(.*?)</div>', block, re.S)
        if not identity or not name_match:
            continue

        file_id = identity.group(1)
        file_name = unescape(name_match.group(1)).strip()
        if not _is_image_entry(block, file_name):
            continue

        if "application/vnd.google-apps.shortcut" in block:
            file_id = _resolve_public_shortcut(file_id)

        if file_id in seen_ids:
            continue
        seen_ids.add(file_id)

        files.append(
            {
                "id": file_id,
                "name": file_name,
                "webContentLink": settings.DRIVE_PUBLIC_DOWNLOAD_URL.format(file_id=file_id),
                "thumbnailLink": settings.DRIVE_PUBLIC_THUMBNAIL_URL.format(file_id=file_id),
            }
        )

    return folder_name, files


def list_public_drive_folder(folder_link: str) -> Tuple[str, List[Dict[str, str]]]:
    folder_id = extract_folder_id(folder_link)
    embedded_url = settings.DRIVE_EMBEDDED_FOLDER_URL.format(folder_id=folder_id)
    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        response = client.get(embedded_url)
    if response.status_code == 404:
        raise FileNotFoundError(f"Google Drive folder {folder_id} was not found")
    if response.status_code in (401, 403):
        raise PermissionError("Google Drive folder requires authentication")
    response.raise_for_status()
    return parse_public_embedded_folder(
        response.text,
        default_name=f"Drive Album {folder_id[:8]}",
    )


def list_drive_files(folder_link: str, access_token: Optional[str] = None) -> List[Dict]:
    if not access_token:
        _, files = list_public_drive_folder(folder_link)
        return files

    service = get_drive_service(access_token)
    folder_id = extract_folder_id(folder_link)
    query = f"'{folder_id}' in parents and mimeType contains 'image/' and trashed = false"

    files = []
    page_token = None

    while True:
        results = service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name, webContentLink, thumbnailLink)",
            pageToken=page_token,
        ).execute()

        files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break

    return files

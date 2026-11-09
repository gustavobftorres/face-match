import re
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

def get_drive_service(access_token: str):
    creds = Credentials(token=access_token)
    return build("drive", "v3", credentials=creds)

def extract_folder_id(url: str) -> str:
    match = re.search(r"folders/([a-zA-Z0-9-_]+)", url)
    if match:
        return match.group(1)
    match = re.search(r"id=([a-zA-Z0-9-_]+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract a valid Google Drive folder ID from the provided link: {url!r}")

def list_drive_files(folder_link: str, access_token: str):
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
            pageToken=page_token
        ).execute()
        
        files.extend(results.get("files", []))
        page_token = results.get("nextPageToken")
        if not page_token:
            break
            
    return files

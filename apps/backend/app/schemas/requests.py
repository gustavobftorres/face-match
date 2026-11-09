from pydantic import BaseModel

class ScanRequest(BaseModel):
    drive_link: str
    target_face: str
    access_token: str

import os
import traceback
from fastapi import APIRouter, HTTPException
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from app.core.config import settings
from app.schemas.auth import OAuthCallbackRequest, OAuthTokenResponse

os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

router = APIRouter()

SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
]

def build_flow() -> Flow:
    return Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI,
    )

@router.get("/google/url")
async def google_auth_url():
    flow = build_flow()
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return {"url": authorization_url, "code_verifier": flow.code_verifier}

@router.post("/google/callback", response_model=OAuthTokenResponse)
async def google_auth_callback(body: OAuthCallbackRequest):
    try:
        flow = build_flow()
        flow.fetch_token(code=body.code, code_verifier=body.code_verifier)
        credentials = flow.credentials

        user_info_service = build("oauth2", "v2", credentials=credentials)
        user_info = user_info_service.userinfo().get().execute()

        return OAuthTokenResponse(
            access_token=credentials.token,
            email=user_info.get("email", ""),
        )
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

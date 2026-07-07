"""Shared Google OAuth for Gmail + Calendar.

First use opens a browser for consent; the refresh token is cached at
data/token.json so subsequent runs are silent.
"""

import json
from pathlib import Path

from config.settings import DATA_DIR, settings
from core.logger import get_logger

log = get_logger("google_auth")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
]
TOKEN_PATH = DATA_DIR / "token.json"


def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not settings.has_google:
        raise RuntimeError("Google not configured — set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in .env")

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception as e:
            log.warning("Token refresh failed (%s) — re-running consent flow", e)

    client_config = {
        "installed": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    creds = flow.run_local_server(port=8080, prompt="consent")
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def gmail_service():
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=get_credentials(), cache_discovery=False)


def calendar_service():
    from googleapiclient.discovery import build

    return build("calendar", "v3", credentials=get_credentials(), cache_discovery=False)

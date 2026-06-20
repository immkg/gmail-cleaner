import time
import random
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import SCOPES, TOKEN_FILE, CREDS_FILE, MAX_RETRIES

def get_gmail_service():
    creds = None

    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds, cache_discovery=False)

def gmail_call(request):
    for attempt in range(MAX_RETRIES):
        try:
            result = request.execute(num_retries=3)
            return result
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            if status in (429, 500, 502, 503, 504):
                wait = min(60, 2 ** attempt) + random.random()
                print(f"\nHTTP {status} retry {attempt+1}/{MAX_RETRIES} wait={wait:.1f}s")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("Max retries exceeded")

def trash_email(gmail_id):
    service = get_gmail_service()
    try:
        service.users().messages().trash(userId="me", id=gmail_id).execute()
        return True
    except Exception as e:
        return str(e)

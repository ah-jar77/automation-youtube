"""
رفع الفيديوهات على يوتيوب عبر YouTube Data API v3
"""

import os
import pickle
import logging
from pathlib import Path
from typing import Optional, List
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES          = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS  = os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secrets.json")
TOKEN_PICKLE    = "youtube_token.pickle"


class YouTubeUploader:
    def __init__(self):
        self.service = self._get_service()

    # ── المصادقة ────────────────────────────────────────────────

    def _get_service(self):
        """يُنشئ خدمة YouTube مع OAuth 2.0"""
        creds = None

        if Path(TOKEN_PICKLE).exists():
            with open(TOKEN_PICKLE, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow  = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
                creds = flow.run_local_server(port=8088)

            with open(TOKEN_PICKLE, "wb") as f:
                pickle.dump(creds, f)

        return build("youtube", "v3", credentials=creds)

    # ── الرفع ────────────────────────────────────────────────────

    def upload(
        self,
        video_path: str,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        category_id: str = "22",
        privacy: str = "public",
    ) -> str:
        """
        يرفع الفيديو على يوتيوب ويُعيد رابطه.
        """
        body = {
            "snippet": {
                "title":       "#اكسبلور #fypシ #ترند #مالي_خلق_احط_هاشتاقات #رياكشن #ضحك #shortvideo #تيك_توك #لايك",
                "description": " ",
                "tags":        tags or [],
                "categoryId":  category_id,
            },
            "status": {
                "privacyStatus":           privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_path,
            mimetype    = "video/*",
            resumable   = True,
            chunksize   = 1024 * 1024 * 5,   # 5 MB
        )

        request = self.service.videos().insert(
            part  = "snippet,status",
            body  = body,
            media_body = media,
        )

        logger.info(f"▶️ بدء الرفع على يوتيوب: {title}")
        response = None

        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                logger.info(f"   يوتيوب: {pct}%")

        video_id = response["id"]
        url      = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"✅ يوتيوب اكتمل: {url}")
        return url

    # ── اختبار الاتصال ──────────────────────────────────────────

    def test_connection(self) -> bool:
        try:
            self.service.channels().list(part="id", mine=True).execute()
            return True
        except Exception as e:
            logger.error(f"يوتيوب test_connection فشل: {e}")
            return False

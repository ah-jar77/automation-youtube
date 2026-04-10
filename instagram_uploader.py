"""
نشر فيديوهات Reels على انستاغرام عبر instagrapi
"""

import os
import logging
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError

logger = logging.getLogger(__name__)

IG_USERNAME  = os.getenv("INSTAGRAM_USERNAME")
IG_PASSWORD  = os.getenv("INSTAGRAM_PASSWORD")
SESSION_FILE = "instagram_session.json"


class InstagramUploader:
    def __init__(self):
        self.client = self._login()

    # ── تسجيل الدخول ────────────────────────────────────────────

    def _login(self) -> Client:
        """يسجّل الدخول ويحفظ الجلسة لإعادة الاستخدام"""
        cl = Client()
        cl.delay_range = [2, 5]    # تأخير بشري بين الطلبات

        if Path(SESSION_FILE).exists():
            try:
                cl.load_settings(SESSION_FILE)
                cl.login(IG_USERNAME, IG_PASSWORD)
                cl.get_timeline_feed()          # تحقق من صلاحية الجلسة
                logger.info("✅ انستاغرام: استُعيدت الجلسة المحفوظة")
                return cl
            except (LoginRequired, ClientError):
                logger.warning("⚠️ انستاغرام: الجلسة منتهية، إعادة تسجيل الدخول...")

        cl.login(IG_USERNAME, IG_PASSWORD)
        cl.dump_settings(SESSION_FILE)
        logger.info("✅ انستاغرام: تم تسجيل الدخول وحفظ الجلسة")
        return cl

    # ── رفع الريل ────────────────────────────────────────────────

    def upload_reel(
        self,
        video_path: str,
        caption: str = "",
        thumbnail_path: str | None = None,
    ) -> str:
        """
        ينشر فيديو كـ Reel ويُعيد رابطه.
        """
        logger.info(f"📸 بدء نشر الريل: {video_path}")

        if thumbnail_path and Path(thumbnail_path).exists():
            media = self.client.clip_upload(
                path     = Path(video_path),
                caption  = caption,
                thumbnail = Path(thumbnail_path),
            )
        else:
            media = self.client.clip_upload(
                path    = Path(video_path),
                caption = caption,
            )

        url = f"https://www.instagram.com/reel/{media.code}/"
        logger.info(f"✅ انستاغرام اكتمل: {url}")
        return url

    # ── رفع كـ Post عادي (بديل) ─────────────────────────────────

    def upload_video_post(self, video_path: str, caption: str = "") -> str:
        """
        ينشر فيديو كـ Feed Post (مناسب للفيديوهات القصيرة).
        """
        media = self.client.video_upload(
            path    = Path(video_path),
            caption = caption,
        )
        url = f"https://www.instagram.com/p/{media.code}/"
        logger.info(f"✅ انستاغرام Post: {url}")
        return url

    # ── اختبار الاتصال ──────────────────────────────────────────

    def test_connection(self) -> bool:
        try:
            self.client.get_timeline_feed()
            return True
        except Exception as e:
            logger.error(f"انستاغرام test_connection فشل: {e}")
            return False

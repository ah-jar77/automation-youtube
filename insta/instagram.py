import os
import time
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)

IG_USER_ID   = os.getenv("IG_USER_ID")
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
BASE_URL     = "https://graph.facebook.com/v19.0"

MAX_RETRIES  = 15   # max status checks
RETRY_DELAY  = 8    # seconds between checks


def _check_container_status(container_id: str) -> str:
    """Returns: FINISHED | IN_PROGRESS | ERROR | EXPIRED"""
    res = requests.get(
        f"{BASE_URL}/{container_id}",
        params={"fields": "status_code,status", "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    data = res.json()
    logger.info(f"Container status: {data}")
    return data.get("status_code", "ERROR")


def post_reel(video_url: str, caption: str) -> bool:
    """
    Full flow to post a Reel via Instagram Graph API.
    Returns True on success, False on failure.
    """
    logger.info(f"Starting Instagram Reel post | URL: {video_url}")

    # ── Step 1: Create media container ──
    res = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media",
        params={
            "video_url":   video_url,
            "caption":     caption,
            "media_type":  "REELS",
            "share_to_feed": "true",
            "access_token": ACCESS_TOKEN,
        },
        timeout=30,
    )
    data = res.json()
    logger.info(f"Create container response: {data}")

    if "id" not in data:
        logger.error(f"Failed to create container: {data}")
        return False

    container_id = data["id"]
    logger.info(f"Container created: {container_id}")

    # ── Step 2: Wait for video processing ──
    for attempt in range(MAX_RETRIES):
        time.sleep(RETRY_DELAY)
        status = _check_container_status(container_id)

        if status == "FINISHED":
            logger.info("Video processing complete ✅")
            break
        elif status in ("ERROR", "EXPIRED"):
            logger.error(f"Video processing failed with status: {status}")
            return False
        else:
            logger.info(f"Still processing... attempt {attempt + 1}/{MAX_RETRIES}")
    else:
        logger.error("Timed out waiting for video processing")
        return False

    # ── Step 3: Publish ──
    pub_res = requests.post(
        f"{BASE_URL}/{IG_USER_ID}/media_publish",
        params={
            "creation_id":  container_id,
            "access_token": ACCESS_TOKEN,
        },
        timeout=30,
    )
    pub_data = pub_res.json()
    logger.info(f"Publish response: {pub_data}")

    if "id" in pub_data:
        logger.info(f"Reel published! Media ID: {pub_data['id']} ✅")
        return True
    else:
        logger.error(f"Publish failed: {pub_data}")
        return False

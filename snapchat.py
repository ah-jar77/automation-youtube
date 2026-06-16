import os
import base64
import logging
import time
import requests
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Base API endpoint
BASE_URL = "https://businessapi.snapchat.com/v1"

def update_env_tokens(access_token, refresh_token):
    """Updates the tokens in the current environment and the .env file."""
    os.environ["SNAP_ACCESS_TOKEN"] = access_token
    os.environ["SNAP_REFRESH_TOKEN"] = refresh_token
    
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            
            new_lines = []
            keys_to_update = {
                "SNAP_ACCESS_TOKEN": f'SNAP_ACCESS_TOKEN="{access_token}"\n',
                "SNAP_REFRESH_TOKEN": f'SNAP_REFRESH_TOKEN="{refresh_token}"\n'
            }
            
            for line in lines:
                updated = False
                for key in keys_to_update:
                    if line.startswith(f"{key}="):
                        new_lines.append(keys_to_update[key])
                        del keys_to_update[key]
                        updated = True
                        break
                if not updated:
                    new_lines.append(line)
            
            for key, val in keys_to_update.items():
                new_lines.append(val)
                
            with open(env_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        except Exception as e:
            logger.error(f"Failed to write updated tokens to .env: {e}")

def refresh_access_token() -> str:
    """Refreshes the Snapchat access token and returns it."""
    client_id = os.getenv("SNAP_CLIENT_ID")
    client_secret = os.getenv("SNAP_CLIENT_SECRET")
    refresh_token = os.getenv("SNAP_REFRESH_TOKEN")
    
    if not client_id or not client_secret or not refresh_token:
        logger.error("Snapchat OAuth credentials missing from environment.")
        return ""

    url = "https://accounts.snapchat.com/accounts/oauth2/token"
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }
    
    try:
        res = requests.post(url, data=data, timeout=15)
        if res.status_code == 200:
            tokens = res.json()
            access_token = tokens.get("access_token")
            # Snapchat might not return a new refresh token, fallback to old one
            new_refresh = tokens.get("refresh_token", refresh_token)
            update_env_tokens(access_token, new_refresh)
            logger.info("Snapchat access token refreshed successfully.")
            return access_token
        else:
            logger.error(f"Failed to refresh Snapchat token. Status: {res.status_code}, Response: {res.text}")
            return ""
    except Exception as e:
        logger.error(f"Exception during Snapchat token refresh: {e}")
        return ""

def encrypt_file(file_path: Path, output_path: Path):
    """Encrypts a file using AES-256-CBC with PKCS7 padding and returns base64 key/iv."""
    # Generate 32-byte key and 16-byte IV
    key = os.urandom(32)
    iv = os.urandom(16)
    
    backend = default_backend()
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    encryptor = cipher.encryptor()
    
    with open(file_path, "rb") as f:
        data = f.read()
        
    # PKCS7 padding
    block_size = 16
    padding_len = block_size - (len(data) % block_size)
    padded_data = data + bytes([padding_len] * padding_len)
    
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    
    with open(output_path, "wb") as f:
        f.write(encrypted_data)
        
    return base64.b64encode(key).decode("utf-8"), base64.b64encode(iv).decode("utf-8")

def test_connection() -> bool:
    """Verifies profile access by retrieving public profiles list."""
    access_token = refresh_access_token()
    if not access_token:
        return False
    
    url = f"{BASE_URL}/me/public_profiles"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=15)
        return res.status_code == 200
    except Exception as e:
        logger.error(f"Snapchat test_connection failed: {e}")
        return False

def upload_and_post_to_spotlight(video_path: Path, caption: str) -> bool:
    """
    Encrypts the video, uploads it to Snapchat, waits for processing, and publishes to Spotlight.
    """
    profile_id = os.getenv("SNAP_PROFILE_ID")
    locale = os.getenv("SNAP_LOCALE", "ar_SA")
    
    if not profile_id:
        logger.error("SNAP_PROFILE_ID is not configured in .env")
        return False
        
    # 1. Refresh access token
    access_token = refresh_access_token()
    if not access_token:
        logger.error("Could not obtain a valid Snapchat access token.")
        return False
        
    # 2. Encrypt the video file
    enc_path = video_path.with_suffix(".mp4.enc")
    logger.info(f"Encrypting video for Snapchat: {video_path} -> {enc_path}")
    try:
        base64_key, base64_iv = encrypt_file(video_path, enc_path)
    except Exception as e:
        logger.error(f"AES encryption failed: {e}")
        return False
        
    try:
        # 3. Create Media Object on Snapchat
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "type": "VIDEO",
            "name": video_path.name,
            "key": base64_key,
            "iv": base64_iv
        }
        
        logger.info("Registering media object container with Snapchat...")
        media_url = f"{BASE_URL}/public_profiles/{profile_id}/media"
        res = requests.post(media_url, headers=headers, json=payload, timeout=20)
        
        if res.status_code != 200:
            logger.error(f"Failed to create Snapchat media object. Status: {res.status_code}, Response: {res.text}")
            return False
            
        media_response = res.json()
        media_data = media_response.get("media", [{}])[0]
        media_id = media_data.get("id")
        upload_url = media_data.get("upload_url")
        
        if not media_id or not upload_url:
            logger.error(f"Invalid Snapchat media registration response: {media_response}")
            return False
            
        logger.info(f"Media registered. ID: {media_id}. Uploading binary encrypted data...")
        
        # 4. Upload the encrypted file via PUT request
        file_size = enc_path.stat().st_size
        with open(enc_path, "rb") as f:
            upload_headers = {
                "Content-Type": "application/octet-stream",
                "Content-Length": str(file_size)
            }
            # Snapchat upload URL is a direct S3 presigned URL
            upload_res = requests.put(upload_url, data=f, headers=upload_headers, timeout=120)
            
        if upload_res.status_code not in (200, 201):
            logger.error(f"Encrypted binary upload failed. Status: {upload_res.status_code}, Response: {upload_res.text}")
            return False
            
        logger.info("Binary upload complete. Polling media processing status...")
        
        # 5. Poll Media status until it becomes READY
        status_url = f"{BASE_URL}/public_profiles/{profile_id}/media/{media_id}"
        max_retries = 20
        retry_delay = 5
        is_ready = False
        
        for attempt in range(max_retries):
            time.sleep(retry_delay)
            status_res = requests.get(status_url, headers=headers, timeout=15)
            if status_res.status_code == 200:
                media_info = status_res.json().get("media", [{}])[0]
                status = media_info.get("status")
                logger.info(f"Polling Snapchat media processing... status: {status} (Attempt {attempt+1}/{max_retries})")
                if status == "READY":
                    is_ready = True
                    break
                elif status in ("FAILED", "ERROR"):
                    logger.error(f"Snapchat media processing failed: {media_info}")
                    return False
            else:
                logger.warning(f"Error checking media status: {status_res.status_code}, response: {status_res.text}")
                
        if not is_ready:
            logger.error("Timed out waiting for Snapchat media processing.")
            return False
            
        # 6. Publish to Spotlight
        logger.info("Publishing media to Spotlight feed...")
        spotlight_url = f"{BASE_URL}/public_profiles/{profile_id}/spotlights"
        spotlight_payload = {
            "media_id": media_id,
            "locale": locale,
            "description": caption[:150]  # Max 150 characters for Spotlight caption
        }
        
        pub_res = requests.post(spotlight_url, headers=headers, json=spotlight_payload, timeout=20)
        if pub_res.status_code in (200, 201):
            logger.info("Snapchat Spotlight post published successfully! ✅")
            return True
        else:
            logger.error(f"Spotlight publish request failed. Status: {pub_res.status_code}, Response: {pub_res.text}")
            return False
            
    except Exception as e:
        logger.error(f"Exception during Snapchat Spotlight upload workflow: {e}")
        return False
    finally:
        # Clean up encrypted file locally
        try:
            if enc_path.exists():
                enc_path.unlink()
                logger.info(f"Cleaned up encrypted file: {enc_path}")
        except Exception as e:
            logger.error(f"Failed to clean up encrypted file: {e}")

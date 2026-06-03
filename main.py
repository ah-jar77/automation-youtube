"""
بوت تلجرام لنشر الفيديو على يوتيوب تلقائياً
Telegram Bot → YouTube Auto Publisher
"""

import os
import logging
import asyncio
import time
from pathlib import Path
from typing import Optional, List, Dict, Set, Union
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyParameters
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from dotenv import load_dotenv
from youtube_uploader import YouTubeUploader
import cloudinary
import cloudinary.uploader
import yt_dlp

load_dotenv()

from insta.instagram import post_reel

# ── إعداد اللوق ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── متغيرات البيئة ────────────────────────────────────────────
BOT_TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID  = int(os.getenv("ALLOWED_USER_ID", "0"))
BOT_PASSWORD      = os.getenv("BOT_PASSWORD", "159951")
INSTAGRAM_CAPTION = os.getenv("INSTAGRAM_CAPTION", "💛كود خصم نون الجديد : 🎀 Rimy 🎀")
# جعل المنصات متغيرة ديناميكياً
ENABLE_YOUTUBE   = os.getenv("ENABLE_YOUTUBE", "true").lower() == "true"
ENABLE_INSTAGRAM = os.getenv("ENABLE_INSTAGRAM", "true").lower() == "true"
ENABLE_TIKTOK_DOWNLOAD = os.getenv("ENABLE_TIKTOK_DOWNLOAD", "false").lower() == "true"
YOUTUBE_UPLOAD_DELAY   = int(os.getenv("YOUTUBE_UPLOAD_DELAY", "180"))

# قائمة بجميع ملفات العميل (client_secrets) المتاحة لـ YouTube
CLIENT_SECRETS_LIST = [
    "client_secrets.json", 
    "client_secrets1.json"
    ]
CURRENT_CLIENT_SECRETS = CLIENT_SECRETS_LIST[0]

def rotate_client_secrets():
    """تبديل ملف client_secrets إلى الملف التالي في القائمة"""
    global CURRENT_CLIENT_SECRETS
    try:
        idx = CLIENT_SECRETS_LIST.index(CURRENT_CLIENT_SECRETS)
        new_idx = (idx + 1) % len(CLIENT_SECRETS_LIST)
    except ValueError:
        new_idx = 0
    CURRENT_CLIENT_SECRETS = CLIENT_SECRETS_LIST[new_idx]
    logger.info(f"🔄 تم تبديل ملف العميل (client_secrets) إلى: {CURRENT_CLIENT_SECRETS}")

# ── أقفال المزامنة والتحكم في التدفق ليوتيوب ──────────────────
youtube_upload_lock = asyncio.Lock()
last_youtube_upload_time = 0.0

# إعداد Cloudinary
cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
)

# إعدادات البروكسي (إذا كنت تستخدم واحداً)
HTTP_PROXY = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
HTTPS_PROXY = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")

# ── مصادقة كلمة المرور ────────────────────────────────────────
auth_sessions: dict[int, float] = {}  # user_id -> last auth timestamp
AUTH_TIMEOUT_HOURS = 24
ACTIVE_YOUTUBE_TOKENS = ["youtube_token.pickle"]
pending_change_auth: set[int] = set() # users waiting to auth for /change

def get_active_channel_name() -> str:
    """إرجاع الاسم المستعار للقناة/القنوات النشطة"""
    names = []
    for token in ACTIVE_YOUTUBE_TOKENS:
        base = "2 مار" if "youtube_token2.pickle" in token else "1 رو"
        if "secret1/" in token:
            names.append(f"{base} (S1)")
        else:
            names.append(base)
    return " + ".join(names)

def toggle_token_path():
    """تبديل مسار التوكنات بين المجلد الرئيسي ومجلد secret1"""
    global ACTIVE_YOUTUBE_TOKENS
    new_tokens = []
    for token in ACTIVE_YOUTUBE_TOKENS:
        if token.startswith("secret1/"):
            new_tokens.append(token.replace("secret1/", ""))
        else:
            new_tokens.append(f"secret1/{token}")
    
    old_names = ", ".join(ACTIVE_YOUTUBE_TOKENS)
    ACTIVE_YOUTUBE_TOKENS = new_tokens
    logger.info(f"🔄 تم تبديل مسار التوكنات: {old_names} -> {', '.join(ACTIVE_YOUTUBE_TOKENS)}")

def _is_authenticated(user_id: int) -> bool:
    """يتحقق إذا كان المستخدم مصادقاً خلال آخر 24 ساعة"""
    if user_id in auth_sessions:
        import time
        elapsed = time.time() - auth_sessions[user_id]
        hours = elapsed / 3600
        return hours < AUTH_TIMEOUT_HOURS
    return False

DOWNLOADS_DIR = Path("downloads")
DOWNLOADS_DIR.mkdir(exist_ok=True)

# ── مُعالجات الأوامر ──────────────────────────────────────────

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تسجيل الدخول بكلمة المرور"""
    user_id = update.effective_user.id
    
    if _is_authenticated(user_id):
        await update.message.reply_text(f"✅ أنت مسجل بالفعل.\nالقناة النشطة: *{get_active_channel_name()}*", parse_mode="Markdown")
        return
    
    await update.message.reply_text(f"\nالرجاء إدخال كلمة المرور:", parse_mode="Markdown")


async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة كلمة المرور"""
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    # إذا لم يكن المستخدم يحاول تغيير القناة، وكان مسجلاً بالفعل، نتجاهل الرسالة أو نفحص إذا كان رابط تيك توك
    if _is_authenticated(user_id) and user_id not in pending_change_auth:
        text = update.message.text.strip()
        if ENABLE_TIKTOK_DOWNLOAD and ("tiktok.com" in text):
            asyncio.create_task(handle_tiktok_link(update, context))
        return
    
    import time
    if password == BOT_PASSWORD:
        if user_id in pending_change_auth:
            pending_change_auth.remove(user_id)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📺 القناة الأولى (1)", callback_data="set_yt_1")],
                [InlineKeyboardButton("📺 القناة الثانية (2)", callback_data="set_yt_2")],
                [InlineKeyboardButton("📺 القناتين (1 + 2)", callback_data="set_yt_both")]
            ])
            await update.message.reply_text("✅ تم التحقق. اختر القناة المراد تفعيلها:", reply_markup=keyboard)
            return

        auth_sessions[user_id] = time.time()
        await update.message.reply_text(f"✅ تم تسجيل الدخول بنجاح!\nالقناة النشطة: *{get_active_channel_name()}*", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ كلمة المرور خاطئة.")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """رسالة الترحيب"""
    user_id = update.effective_user.id
    
    if not _is_authenticated(user_id):
        await update.message.reply_text(
            "🔒 هذا البوت محمي بكلمة مرور.\n"
            "أرسل /login لتسجيل الدخول."
        )
        return
    
    platforms = []
    if ENABLE_YOUTUBE:
        platforms.append("▶️ يوتيوب")
    if ENABLE_INSTAGRAM:
        platforms.append("📸 انستاغرام")
    
    platforms_text = "\n".join(platforms) if platforms else "❌ لا توجد منصات مفعلة"
    
    text = (
        "👋 *مرحباً!*\n\n"
        f"القناة النشطة حالياً: *{get_active_channel_name()}*\n\n"
        f"أرسل لي فيديو وسأنشره تلقائياً على:\n{platforms_text}\n\n"
        "📌 *أوامر متاحة:*\n"
        "/start — عرض هذه الرسالة\n"
        "/status — حالة الاتصال بالمنصات\n"
        # "/change — تغيير قناة يوتيوب\n"
        "/help — المساعدة\n\n"
        "⚡ أرسل الفيديو مباشرة للبدء!"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def change_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بدء عملية تغيير القناة"""
    user_id = update.effective_user.id
    if not _is_authenticated(user_id):
        await update.message.reply_text("🔒 يرجى تسجيل الدخول أولاً بـ /login")
        return

    pending_change_auth.add(user_id)
    await update.message.reply_text("🔐 لتغيير القناة، يرجى إدخال كلمة مرور البوت للتأكيد:")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check connection status for enabled platforms."""
    user_id = update.effective_user.id
    if not _is_authenticated(user_id):
        await update.message.reply_text("🔒 يرجى تسجيل الدخول بـ /login")
        return

    if not _is_allowed(update):
        await update.message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return

    msg = await update.message.reply_text("🔍 جاري فحص الاتصال...")
    lines = []

    if ENABLE_YOUTUBE:
        for token in ACTIVE_YOUTUBE_TOKENS:
            try:
                uploader = YouTubeUploader(token_file=token, client_secrets_file=CURRENT_CLIENT_SECRETS)
                yt_ok = uploader.test_connection()
                status_text = "متصل" if yt_ok else "غير متصل"
                ch_name = "2 مار" if "youtube_token2.pickle" in token else "1 رو"
                if "secret1/" in token: ch_name += " (S1)"
                lines.append(f"{'✅' if yt_ok else '❌'} يوتيوب ({ch_name}: {status_text})")
            except Exception as e:
                logger.error(f"YouTube status check failed for {token}: {e}")
                lines.append(f"❌ يوتيوب ({token})")

    if ENABLE_INSTAGRAM:
        lines.append("✅ انستاغرام (مفعل)")

    if not lines:
        lines.append("⚠️ لا توجد منصات مفعلة")

    text = "📊 *حالة المنصات:*\n\n" + "\n".join(lines)
    await msg.edit_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_authenticated(user_id):
        await update.message.reply_text("🔒 يرجى تسجيل الدخول بـ /login")
        return

    text = (
        "📖 *المساعدة:*\n\n"
        "1️⃣ أرسل الفيديو كملف (File) لا كرسالة مضغوطة\n"
        "2️⃣ أضف وصفاً في كابشن الفيديو (اختياري)\n"
        "   • السطر الأول → عنوان يوتيوب\n"
        "   • باقي النص  → الوصف والهاشتاقات\n\n"
        "🎬 *مثال:*\n"
        "`عنوان الفيديو هنا\n"
        "وصف جميل للفيديو\n"
        "#فيديو #يوتيوب`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def _send_status_reply(message, text: str):
    """يرسل رسالة حالة كرد مباشر على رسالة الفيديو الأصلية."""
    return await message.reply_text(
        text,
        reply_parameters=ReplyParameters(
            message_id=message.message_id,
            chat_id=message.chat_id,
            allow_sending_without_reply=True,
        ),
        disable_web_page_preview=True,
    )


async def _update_status_reply(message, status_message, text: str):
    """يحدّث رسالة الحالة، ويرسل رسالة بديلة إن تعذر التعديل."""
    try:
        await status_message.edit_text(text, disable_web_page_preview=True)
        return status_message
    except Exception as e:
        logger.warning(f"تعذر تعديل رسالة الحالة الحالية: {e}")
        return await _send_status_reply(message, text)


async def _upload_to_cloudinary(file_path: Path) -> Optional[str]:
    """يرفع الفيديو إلى Cloudinary ويُعيد الرابط العام."""
    try:
        result = cloudinary.uploader.upload(
            str(file_path),
            resource_type="video",
            folder="instagram_reels",
            overwrite=True,
        )
        return result.get("secure_url")
    except Exception as e:
        logger.error(f"Fails to upload to Cloudinary: {e}")
        return None


def _format_error_text(error: object, fallback: str = "خطأ غير معروف") -> str:
    """يحوّل الاستثناء إلى سطر قصير مناسب لرسائل تلجرام."""
    text = " ".join(str(error).split()).strip()
    if not text:
        return fallback
    if len(text) > 280:
        return f"{text[:277]}..."
    return text


# ── معالج الفيديو الرئيسي ─────────────────────────────────────

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """يستقبل الفيديو ويبدأ النشر"""
    user_id = update.effective_user.id
    if not _is_authenticated(user_id):
        await update.message.reply_text("🔒 يرجى تسجيل الدخول بـ /login")
        return
    
    if not _is_allowed(update):
        await update.message.reply_text("⛔ غير مصرح لك باستخدام هذا البوت.")
        return

    message = update.message
    video   = message.video or message.document

    if not video:
        await message.reply_text("❌ يرجى إرسال ملف فيديو.")
        return

    # ── استخراج العنوان والوصف من الكابشن ──
    caption  = message.caption or ""
    lines    = caption.strip().splitlines()
    title    = lines[0].strip() if lines else "فيديو جديد"
    desc     = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    hashtags = _extract_hashtags(desc)

    status_msg = await _send_status_reply(
        message,
        "\n".join([
            f"⏳ معالجة الفيديو ({get_active_channel_name()})",
            f"العنوان: {title}",
            "المرحلة: جاري التحميل من تيليجرام",
        ]),
    )

    # ── تحميل الفيديو من تلجرام ──
    file_path = DOWNLOADS_DIR / f"{video.file_id}.mp4"
    try:
        tg_file = await context.bot.get_file(video.file_id)
        await tg_file.download_to_drive(file_path)
        logger.info(f"تم تحميل الفيديو: {file_path}")
    except Exception as e:
        logger.error(f"فشل تحميل الفيديو: {e}")
        status_msg = await _update_status_reply(
            message,
            status_msg,
            "\n".join([
                f"❌ فشل الفيديو ({get_active_channel_name()})",
                f"العنوان: {title}",
                "المرحلة: تحميل الملف من تيليجرام",
                f"السبب: {_format_error_text(e)}",
            ]),
        )
        return

    status_msg = await _update_status_reply(
        message,
        status_msg,
        "\n".join([
            "⏳ هذا الفيديو قيد المعالجة",
            f"العنوان: {title}",
            "المرحلة: تم التحميل من تيليجرام",
            "الخطوة التالية: جاري الرفع إلى المنصات",
        ]),
    )

    await process_and_upload_video(message, file_path, title, desc, hashtags, status_msg)

async def handle_tiktok_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    text = message.text.strip()
    
    lines = text.splitlines()
    url = lines[0].strip()
    title = lines[1].strip() if len(lines) > 1 else "فيديو تيك توك"
    desc = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""
    hashtags = _extract_hashtags(desc)
    
    status_msg = await _send_status_reply(
        message,
        "\n".join([
            f"⏳ معالجة رابط تيك توك ({get_active_channel_name()})",
            f"العنوان: {title}",
            "المرحلة: جاري التحميل من تيك توك",
        ]),
    )
    
    import time
    file_id = f"tiktok_{int(time.time())}"
    file_path = DOWNLOADS_DIR / f"{file_id}.mp4"
    
    ydl_opts = {
        'outtmpl': str(file_path),
        'format': 'best', # Get the best available single-file format (often highest quality for TikTok)
        'quiet': True,
        'no_warnings': True,
    }
    
    def download_video():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
    try:
        await asyncio.to_thread(download_video)
        logger.info(f"تم تحميل فيديو تيك توك: {file_path}")
    except Exception as e:
        logger.error(f"فشل تحميل تيك توك: {e}")
        await _update_status_reply(
            message,
            status_msg,
            f"❌ فشل تحميل الفيديو من تيك توك\nالسبب: {_format_error_text(e)}"
        )
        return
        
    status_msg = await _update_status_reply(
        message,
        status_msg,
        "\n".join([
            "⏳ هذا الفيديو قيد المعالجة",
            f"العنوان: {title}",
            "المرحلة: تم التحميل من تيك توك",
            "الخطوة التالية: جاري الرفع إلى المنصات",
        ]),
    )

    await process_and_upload_video(message, file_path, title, desc, hashtags, status_msg)

async def process_and_upload_video(message, file_path: Path, title: str, desc: str, hashtags: list[str], status_msg) -> None:

    # ── رفع على يوتيوب ──
    yt_results = [] # list of (url, err)
    if ENABLE_YOUTUBE:
        for token in ACTIVE_YOUTUBE_TOKENS:
            current_token = token
            # منطق العنوان المخصص للقناة الثانية
            current_title = title
            if "youtube_token2.pickle" in current_token:
                current_title = "كود خصم نون mar110k"

            async with youtube_upload_lock:

                status_msg = await _update_status_reply(
                    message,
                    status_msg,
                    "\n".join([
                        "⏳ هذا الفيديو قيد المعالجة",
                        f"العنوان: {title}",
                        f"المرحلة: جاري الرفع إلى يوتيوب ({current_token})...",
                    ])
                )

                try_token = current_token
                uploaded_url = None
                last_error = None
                
                max_attempts = len(CLIENT_SECRETS_LIST) * 2
                for combo_attempt in range(max_attempts):
                    secrets_file = CURRENT_CLIENT_SECRETS
                    try:
                        uploader = YouTubeUploader(token_file=try_token, client_secrets_file=secrets_file)
                        url = uploader.upload(
                            video_path  = str(file_path),
                            title       = current_title,
                            description = desc or f"{current_title}\n\n{' '.join(hashtags)}",
                            tags        = hashtags,
                        )
                        uploaded_url = url
                        logger.info(f"يوتيوب ✅ (ملف: {secrets_file} | توكن: {try_token}): {url}")
                        break
                    except Exception as e:
                        last_error = e
                        error_str = str(e).lower()
                        if "quota" in error_str or "limit" in error_str or "exceeded" in error_str:
                            if combo_attempt % 2 == 0:
                                logger.warning(f"⚠️ انتهاء الكوتا للتوكن ({try_token}) لـ {secrets_file}. جاري تبديل المجلد والمحاولة مجدداً...")
                                toggle_token_path()
                                try_token = f"secret1/{current_token}" if not current_token.startswith("secret1/") else current_token.replace("secret1/", "")
                            else:
                                logger.warning(f"⚠️ انتهاء الكوتا لكلا مجلدي التوكن لـ {secrets_file}. جاري تبديل client_secrets...")
                                rotate_client_secrets()
                        else:
                            break
                            
                if uploaded_url:
                    yt_results.append((uploaded_url, None))
                else:
                    yt_results.append((None, _format_error_text(last_error)))
                    logger.error(f"يوتيوب ❌ فشل نهائي للتوكن {current_token}: {last_error}")

    # ── رفع على انستاغرام ──
    ig_url = None
    ig_err = None
    if ENABLE_INSTAGRAM:
        try:
            status_msg = await _update_status_reply(
                message, status_msg,
                "\n".join([
                    "⏳ هذا الفيديو قيد المعالجة",
                    f"العنوان: {title}",
                    "المرحلة: جاري الرفع إلى انستاغرام",
                    "(يتم الرفع إلى Cloudinary أولاً...)"
                ])
            )
            
            # 1. الرفع إلى Cloudinary للحصول على رابط عمومي
            video_url = await _upload_to_cloudinary(file_path)
            if not video_url:
                ig_err = "فشل الرفع إلى Cloudinary"
            else:
                # 2. النشر عبر API الرسمية
                success = post_reel(video_url, INSTAGRAM_CAPTION)
                if success:
                    ig_url = "تم النشر بنجاح ✅"
                else:
                    ig_err = "فشل النشر عبر Instagram API"
        except Exception as e:
            ig_err = _format_error_text(e)
            logger.error(f"انستاغرام ❌: {e}")

    # ── حذف الملف محلياً (سواءً نجح الرفع أو فشل) ──
    video_deleted = False
    delete_error = None
    file_size_mb = 0.0
    try:
        if file_path.exists():
            file_size_mb = file_path.stat().st_size / (1024*1024)
            file_path.unlink()
            video_deleted = True
            logger.info(f"تم حذف الفيديو: {file_path}")
        else:
            logger.warning(f"الملف غير موجود لحذفه: {file_path}")
    except Exception as e:
        delete_error = str(e)
        logger.error(f"فشل حذف الفيديو: {e}")

    # ── التقرير النهائي ──
    result_lines = []
    if ENABLE_YOUTUBE:
        for i, (url, err) in enumerate(yt_results):
            # نستخدم التوكنات الحالية للحصول على الاسم الصحيح في التقرير
            if i < len(ACTIVE_YOUTUBE_TOKENS):
                token = ACTIVE_YOUTUBE_TOKENS[i]
                ch_name = "2 مار" if "youtube_token2.pickle" in token else "1 رو"
                if "secret1/" in token: ch_name += " (S1)"
                
                if url:
                    result_lines.append(f"▶️ يوتيوب ({ch_name}): {url}")
                else:
                    result_lines.append(f"▶️ يوتيوب ({ch_name}): ❌ {err or 'فشل'}")
    
    if ENABLE_INSTAGRAM:
        if ig_url:
            result_lines.append(f"📸 انستاغرام: {ig_url}")
        else:
            result_lines.append(f"📸 انستاغرام: ❌ {ig_err or 'فشل'}")

    result_text = "\n".join(result_lines) if result_lines else "⚠️ لم يتم تفعيل أي منصة"

    uploaded_any = any(res[0] for res in yt_results) or (ig_url is not None)
    final = (
        f"{'✅ نجح الفيديو' if uploaded_any else '❌ فشل الفيديو'} ({get_active_channel_name()})\n"
        f"العنوان: {title}\n"
        f"{result_text}\n"
        f"الحجم: {file_size_mb:.2f} MB\n"
        f"الحذف المحلي: {'✅ تم' if video_deleted else f'❌ لم يُحذف: {_format_error_text(delete_error)}' if delete_error else '❌ لم يُحذف'}"
    )
    await _update_status_reply(message, status_msg, final)


# ── دوال مساعدة ───────────────────────────────────────────────

def _is_allowed(update: Update) -> bool:
    """يتحقق أن المستخدم هو صاحب البوت"""
    uid = update.effective_user.id
    if ALLOWED_USER_ID and uid != ALLOWED_USER_ID:
        logger.warning(f"وصول غير مصرح: user_id={uid}")
        return False
    return True


def _extract_hashtags(text: str) -> list[str]:
    """يستخرج الهاشتاقات من النص"""
    return [w.lstrip("#") for w in text.split() if w.startswith("#")]


async def handle_change_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة اختيار القناة من الأزرار"""
    query = update.callback_query
    await query.answer()
    
    global ACTIVE_YOUTUBE_TOKENS
    data = query.data
    
    is_secret = any("secret1/" in t for t in ACTIVE_YOUTUBE_TOKENS)
    prefix = "secret1/" if is_secret else ""

    if data == "set_yt_1":
        ACTIVE_YOUTUBE_TOKENS = [f"{prefix}youtube_token.pickle"]
    elif data == "set_yt_2":
        ACTIVE_YOUTUBE_TOKENS = [f"{prefix}youtube_token2.pickle"]
    elif data == "set_yt_both":
        ACTIVE_YOUTUBE_TOKENS = [f"{prefix}youtube_token.pickle", f"{prefix}youtube_token2.pickle"]
    else:
        return

    channel_name = get_active_channel_name()
    await query.edit_message_text(f"✅ تم تغيير القناة النشطة إلى: *{channel_name}*")

async def platform_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تغيير المنصات النشطة"""
    user_id = update.effective_user.id
    if not _is_authenticated(user_id):
        await update.message.reply_text("🔒 يرجى تسجيل الدخول بـ /login")
        return

    keyboard = [
        [InlineKeyboardButton(f"YouTube: {'✅' if ENABLE_YOUTUBE else '❌'}", callback_data="toggle_yt")],
        [InlineKeyboardButton(f"Instagram: {'✅' if ENABLE_INSTAGRAM else '❌'}", callback_data="toggle_ig")],
        [InlineKeyboardButton(f"TikTok Download: {'✅' if ENABLE_TIKTOK_DOWNLOAD else '❌'}", callback_data="toggle_tk")]
    ]
    await update.message.reply_text("⚙️ اختر المنصات النشطة لنشر الفيديوهات:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_toggle_platform(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة أزرار تبديل المنصات"""
    query = update.callback_query
    await query.answer()
    
    global ENABLE_YOUTUBE, ENABLE_INSTAGRAM, ENABLE_TIKTOK_DOWNLOAD
    data = query.data
    
    if data == "toggle_yt":
        ENABLE_YOUTUBE = not ENABLE_YOUTUBE
    elif data == "toggle_ig":
        ENABLE_INSTAGRAM = not ENABLE_INSTAGRAM
    elif data == "toggle_tk":
        ENABLE_TIKTOK_DOWNLOAD = not ENABLE_TIKTOK_DOWNLOAD

    keyboard = [
        [InlineKeyboardButton(f"YouTube: {'✅' if ENABLE_YOUTUBE else '❌'}", callback_data="toggle_yt")],
        [InlineKeyboardButton(f"Instagram: {'✅' if ENABLE_INSTAGRAM else '❌'}", callback_data="toggle_ig")],
        [InlineKeyboardButton(f"TikTok Download: {'✅' if ENABLE_TIKTOK_DOWNLOAD else '❌'}", callback_data="toggle_tk")]
    ]
    try:
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        pass

# ── تشغيل البوت ───────────────────────────────────────────────

from telegram.request import HTTPXRequest

def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("❌ TELEGRAM_BOT_TOKEN غير موجود في ملف .env")

    # إعداد الطلب مع دعم البروكسي
    request = None
    if HTTP_PROXY or HTTPS_PROXY:
        proxy_url = HTTPS_PROXY or HTTP_PROXY
        try:
            request = HTTPXRequest(proxy_url=proxy_url)
            logger.info(f"🔌 يستخدم البروكسي: {proxy_url}")
        except Exception as e:
            logger.warning(f"فشل إعداد البروكسي: {e}")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )
    
    if request:
        app.bot._request = request

    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("ahmed",  start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("change", change_channel))
    app.add_handler(CommandHandler("platform", platform_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password))
    app.add_handler(
        MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video)
    )
    app.add_handler(CallbackQueryHandler(handle_change_choice, pattern="^set_yt_"))
    app.add_handler(CallbackQueryHandler(handle_toggle_platform, pattern="^toggle_"))

    logger.info("🤖 البوت يعمل الآن...")
    
    # Python 3.12+ fix: Ensure an event loop exists before calling run_polling
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

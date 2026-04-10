"""
بوت تلجرام لنشر الفيديو على يوتيوب تلقائياً
Telegram Bot → YouTube Auto Publisher
"""

import os
import logging
import asyncio
from pathlib import Path
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

load_dotenv()

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
ENABLE_YOUTUBE   = os.getenv("ENABLE_YOUTUBE", "true").lower() == "true"
ENABLE_INSTAGRAM = False # os.getenv("ENABLE_INSTAGRAM", "false").lower() == "true"

# إعدادات البروكسي (إذا كنت تستخدم واحداً)
HTTP_PROXY = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
HTTPS_PROXY = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")

# ── مصادقة كلمة المرور ────────────────────────────────────────
auth_sessions: dict[int, float] = {}  # user_id -> last auth timestamp
AUTH_TIMEOUT_HOURS = 24
CURRENT_YOUTUBE_TOKEN = "youtube_token.pickle"
pending_change_auth: set[int] = set() # users waiting to auth for /change

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
        await update.message.reply_text("✅ أنت مسجل بالفعل. الصلاحية صالحة لـ 24 ساعة.")
        return
    
    await update.message.reply_text("🔐 الرجاء إدخال كلمة المرور:")


async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالجة كلمة المرور"""
    user_id = update.effective_user.id
    password = update.message.text.strip()
    
    # إذا لم يكن المستخدم يحاول تغيير القناة، وكان مسجلاً بالفعل، نتجاهل الرسالة
    if _is_authenticated(user_id) and user_id not in pending_change_auth:
        return
    
    import time
    if password == BOT_PASSWORD:
        if user_id in pending_change_auth:
            pending_change_auth.remove(user_id)
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📺 القناة الأولى (1)", callback_data="set_yt_1")],
                [InlineKeyboardButton("📺 القناة الثانية (2)", callback_data="set_yt_2")]
            ])
            await update.message.reply_text("✅ تم التحقق. اختر القناة المراد تفعيلها:", reply_markup=keyboard)
            return

        auth_sessions[user_id] = time.time()
        await update.message.reply_text("✅ تم تسجيل الدخول بنجاح! الصلاحية صالحة لـ 24 ساعة.")
    else:
        await update.message.reply_text("❌ كلمة المرور incorrectة. حاول مجدداً.")


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
        try:
            uploader = YouTubeUploader(token_file=CURRENT_YOUTUBE_TOKEN)
            yt_ok = uploader.test_connection()
            status_text = "متصل" if yt_ok else "غير متصل"
            token_name = "القناة 1" if CURRENT_YOUTUBE_TOKEN == "youtube_token.pickle" else "القناة 2"
            lines.append(f"{'✅' if yt_ok else '❌'} يوتيوب ({token_name}: {status_text})")
        except Exception as e:
            logger.error(f"YouTube status check failed: {e}")
            lines.append("❌ يوتيوب")

    if ENABLE_INSTAGRAM:
        lines.append("⏸️ انستاغرام (معطل)")

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
            "⏳ هذا الفيديو قيد المعالجة",
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
                "❌ فشل هذا الفيديو",
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

    # ── رفع على يوتيوب ──
    yt_url  = None
    yt_err  = None
    if ENABLE_YOUTUBE:
        try:
            uploader = YouTubeUploader(token_file=CURRENT_YOUTUBE_TOKEN)
            yt_url   = uploader.upload(
                video_path  = str(file_path),
                title       = title,
                description = desc or f"{title}\n\n{' '.join(hashtags)}",
                tags        = hashtags,
            )
            logger.info(f"يوتيوب ✅: {yt_url}")
        except Exception as e:
            yt_err = _format_error_text(e)
            logger.error(f"يوتيوب ❌: {e}")

    # ── رفع على انستاغرام ──
    ig_url = None
    ig_err = None
    if ENABLE_INSTAGRAM:
        ig_err = "انستاغرام معطل حالياً"

    # ── حذف الملف بعد نجاح الرفع ──
    video_deleted = False
    delete_error = None
    file_size_mb = file_path.stat().st_size / (1024*1024)
    
    uploaded_any = (yt_url is not None) or (ig_url is not None)
    if uploaded_any:
        try:
            file_path.unlink()
            video_deleted = True
            logger.info(f"تم حذف الفيديو: {file_path}")
        except Exception as e:
            delete_error = str(e)
            logger.error(f"فشل حذف الفيديو: {e}")

    # ── التقرير النهائي ──
    result_lines = []
    if ENABLE_YOUTUBE:
        if yt_url:
            result_lines.append(f"▶️ يوتيوب: {yt_url}")
        else:
            result_lines.append(f"▶️ يوتيوب: ❌ {yt_err or 'فشل'}")
    
    if ENABLE_INSTAGRAM:
        if ig_url:
            result_lines.append(f"📸 انستاغرام: {ig_url}")
        else:
            result_lines.append(f"📸 انستاغرام: ❌ {ig_err or 'فشل'}")

    result_text = "\n".join(result_lines) if result_lines else "⚠️ لم يتم تفعيل أي منصة"

    final = (
        f"{'✅ نجح هذا الفيديو' if uploaded_any else '❌ فشل هذا الفيديو'}\n"
        f"العنوان: {title}\n"
        f"{result_text}\n"
        f"الحجم: {file_size_mb:.2f} MB\n"
        f"الحذف المحلي: {'✅ تم' if video_deleted else '❌ لم يُحذف' if not uploaded_any else f'❌ {_format_error_text(delete_error)}'}"
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
    
    global CURRENT_YOUTUBE_TOKEN
    data = query.data
    
    if data == "set_yt_1":
        CURRENT_YOUTUBE_TOKEN = "youtube_token.pickle"
        channel_name = "القناة الأولى (1)"
    elif data == "set_yt_2":
        CURRENT_YOUTUBE_TOKEN = "youtube_token2.pickle"
        channel_name = "القناة الثانية (2)"
    else:
        return

    await query.edit_message_text(f"✅ تم تغيير القناة النشطة إلى: *{channel_name}*\nسيتم استخدام ملف: `{CURRENT_YOUTUBE_TOKEN}`", parse_mode="Markdown")

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
    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("change", change_channel))
    app.add_handler(CommandHandler("help",   help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_password))
    app.add_handler(
        MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video)
    )
    app.add_handler(CallbackQueryHandler(handle_change_choice, pattern="^set_yt_"))

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

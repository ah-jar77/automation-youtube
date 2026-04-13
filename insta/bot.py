import os
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler,
    filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

from instagram import post_reel

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Config from environment variables
# ──────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN")
FIXED_CAPTION    = os.getenv("INSTAGRAM_CAPTION", "💛كود خصم نون الجديد : 🎀 Rimy 🎀")
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "")   # comma-separated Telegram user IDs (optional)

cloudinary.config(
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key    = os.getenv("CLOUDINARY_API_KEY"),
    api_secret = os.getenv("CLOUDINARY_API_SECRET"),
)

# ──────────────────────────────────────────────
# Conversation state
# ──────────────────────────────────────────────
WAITING_FOR_TIME = 1

# ──────────────────────────────────────────────
# Scheduler
# ──────────────────────────────────────────────
scheduler = AsyncIOScheduler()


# ──────────────────────────────────────────────
# Helper: check allowed users
# ──────────────────────────────────────────────
def is_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS.strip():
        return True  # no restriction
    return str(user_id) in [u.strip() for u in ALLOWED_USER_IDS.split(",")]


# ──────────────────────────────────────────────
# Helper: download from Telegram → upload to Cloudinary → return URL
# ──────────────────────────────────────────────
async def upload_video_to_cloudinary(bot, file_id: str) -> Optional[str]:
    try:
        file = await bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            logger.info(f"Downloaded video to {tmp.name}")

            result = cloudinary.uploader.upload(
                tmp.name,
                resource_type="video",
                folder="instagram_reels",
                overwrite=True,
            )
            url = result["secure_url"]
            logger.info(f"Uploaded to Cloudinary: {url}")
            return url
    except Exception as e:
        logger.error(f"upload_video_to_cloudinary error: {e}")
        return None


# ──────────────────────────────────────────────
# Scheduled job function (called by APScheduler)
# ──────────────────────────────────────────────
async def scheduled_post(bot, file_id: str, chat_id: int):
    await bot.send_message(chat_id, "⏳ وقت الجدولة وصل! جاري النشر...")
    video_url = await upload_video_to_cloudinary(bot, file_id)
    if not video_url:
        await bot.send_message(chat_id, "❌ فشل رفع الفيديو")
        return

    success = post_reel(video_url, FIXED_CAPTION)
    if success:
        await bot.send_message(chat_id, "✅ تم النشر على Instagram بنجاح!")
    else:
        await bot.send_message(chat_id, "❌ فشل النشر على Instagram")


# ──────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    await update.message.reply_text(
        "👋 أهلاً!\n\n"
        "أرسل لي فيديو وسأنشره كـ *Reel* على Instagram.\n\n"
        "يمكنك اختيار النشر الفوري أو جدولة وقت معين 🕐",
        parse_mode="Markdown"
    )


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return

    video = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("❗ أرسل فيديو MP4 من فضلك")
        return

    context.user_data["video_file_id"] = video.file_id

    keyboard = [
        [InlineKeyboardButton("🚀 نشر الآن", callback_data="post_now")],
        [InlineKeyboardButton("⏰ جدولة لوقت معين", callback_data="schedule")],
    ]
    await update.message.reply_text(
        "📹 استلمت الفيديو!\n\nماذا تريد؟",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "post_now":
        await query.edit_message_text("⏳ جاري الرفع والنشر، انتظر قليلاً...")
        file_id = context.user_data.get("video_file_id")

        video_url = await upload_video_to_cloudinary(context.bot, file_id)
        if not video_url:
            await query.edit_message_text("❌ فشل رفع الفيديو إلى Cloudinary")
            return

        success = post_reel(video_url, FIXED_CAPTION)
        if success:
            await query.edit_message_text("✅ تم النشر على Instagram بنجاح! 🎉")
        else:
            await query.edit_message_text("❌ فشل النشر على Instagram، تحقق من الـ token والصلاحيات")

        return ConversationHandler.END

    elif query.data == "schedule":
        await query.edit_message_text(
            "⏰ أرسل وقت النشر بهذا الشكل:\n"
            "`YYYY-MM-DD HH:MM`\n\n"
            "مثال: `2025-06-15 20:00`",
            parse_mode="Markdown"
        )
        return WAITING_FOR_TIME


async def handle_schedule_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        schedule_dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        await update.message.reply_text(
            "❌ الصيغة غلط! استخدم: `YYYY-MM-DD HH:MM`\nمثال: `2025-06-15 20:00`",
            parse_mode="Markdown"
        )
        return WAITING_FOR_TIME

    if schedule_dt <= datetime.now():
        await update.message.reply_text("❌ الوقت في الماضي! أدخل وقتاً مستقبلياً")
        return WAITING_FOR_TIME

    file_id = context.user_data.get("video_file_id")
    chat_id = update.effective_chat.id

    scheduler.add_job(
        scheduled_post,
        trigger="date",
        run_date=schedule_dt,
        args=[context.bot, file_id, chat_id],
        id=f"reel_{chat_id}_{schedule_dt.timestamp()}",
    )

    await update.message.reply_text(
        f"✅ تم جدولة النشر!\n📅 *{schedule_dt.strftime('%Y-%m-%d الساعة %H:%M')}*\n\n"
        "سأرسل لك إشعاراً عند النشر 👍",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def list_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update.effective_user.id):
        return
    jobs = scheduler.get_jobs()
    if not jobs:
        await update.message.reply_text("📭 لا توجد جدولة مستقبلية حالياً")
        return

    msg = "📋 *الجدولات المستقبلية:*\n\n"
    for job in jobs:
        msg += f"• `{job.id}` ← {job.next_run_time.strftime('%Y-%m-%d %H:%M')}\n"
    await update.message.reply_text(msg, parse_mode="Markdown")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_callback, pattern="^(post_now|schedule)$")],
        states={
            WAITING_FOR_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_schedule_time)
            ]
        },
        fallbacks=[],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("jobs", list_jobs))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    app.add_handler(conv)

    scheduler.start()
    logger.info("🤖 Bot is running...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()

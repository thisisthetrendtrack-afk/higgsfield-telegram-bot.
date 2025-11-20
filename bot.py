import os
import asyncio
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ApplicationBuilder,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from higgsfield_api import HiggsfieldAPI


# GLOBAL STATE
user_sessions = {}


# ---------------------------
# START COMMAND
# ---------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🎬 Text → Video (Soul)", callback_data="text2video")],
        [InlineKeyboardButton("🏞 Image → Video (DoP)", callback_data="image2video")],
    ]

    welcome_text = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "Generate ultra-realistic images & videos using official Higgsfield Cloud.\n\n"
        "✨ Bot by @honeyhoney44\n\n"
        "Select an option below."
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ---------------------------
# INLINE BUTTON HANDLER
# ---------------------------
async def button_handler(update, context):
    q = update.callback_query
    await q.answer()

    chat_id = q.message.chat_id
    user_sessions[chat_id] = {"mode": q.data}

    if q.data == "text2image":
        await q.edit_message_text("📝 Send your text prompt for *Image Generation*.", parse_mode="Markdown")

    elif q.data == "text2video":
        await q.edit_message_text("📝 Send your text prompt for *Soul Video Generation*.", parse_mode="Markdown")

    elif q.data == "image2video":
        await q.edit_message_text("📸 Send an image first. Then send your video prompt.")


# ---------------------------
# MESSAGE HANDLER
# ---------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    if chat_id not in user_sessions:
        await update.message.reply_text("Use /start to open the menu.")
        return

    mode = user_sessions[chat_id]["mode"]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))

    # ---------------------------
    # 1. TEXT → IMAGE
    # ---------------------------
    if mode == "text2image":
        payload = {"prompt": text}

        resp = hf.submit("v1/image", payload)
        job_id = resp["job_set_id"]

        await update.message.reply_text(
            f"🟦 Image generation started.\nRequest ID: `{job_id}`",
            parse_mode="Markdown"
        )

        result = hf.wait_for_result(job_id)

        if result["status"] == "completed":
            await update.message.reply_photo(result["result"][0]["url"])
        else:
            await update.message.reply_text("❌ Failed")

    # ---------------------------
    # 2. TEXT → VIDEO (SOUL)
    # ---------------------------
    elif mode == "text2video":
        payload = {"prompt": text}

        resp = hf.submit("v1/video/soul", payload)
        job_id = resp["job_set_id"]

        await update.message.reply_text(
            f"🎬 Video generation started.\nRequest ID: `{job_id}`",
            parse_mode="Markdown"
        )

        result = hf.wait_for_result(job_id)

        if result["status"] == "completed":
            await update.message.reply_video(result["result"]["url"])
        else:
            await update.message.reply_text("❌ Failed")


# ---------------------------
# PHOTO HANDLER (IMAGE → VIDEO)
# ---------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        await update.message.reply_text("Select Image → Video first using /start.")
        return

    file = await update.message.photo[-1].get_file()
    path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(path)

    user_sessions[chat_id]["image"] = path

    await update.message.reply_text("📌 Image saved. Now send your video prompt.")


# ---------------------------
# REGISTER HANDLERS
# ---------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

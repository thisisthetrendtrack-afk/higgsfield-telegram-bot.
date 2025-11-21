import os
import asyncio
import requests
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ApplicationBuilder,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from higgsfield_api import HiggsfieldAPI

# Admin / Limits
ADMIN_ID = 7872634386
user_counts = {}  # {user_id: number_of_generations}

# Session memory
user_sessions = {}

# ----------------------------------------------------
# START COMMAND
# ----------------------------------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("📸 → 🎬 Image → Video", callback_data="image2video")],
    ]

    welcome_text = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "✨ Bot by @honeyhoney44\n\n"
        "🔔 For premium prompts join: @HiggsMasterBot\n"
        "Each user gets *2 free generations*.\n\n"
        "Choose an option below:"
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ----------------------------------------------------
# BUTTON HANDLER
# ----------------------------------------------------
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    mode = query.data
    chat_id = query.message.chat_id
    user_sessions[chat_id] = {"mode": mode}

    if mode == "text2image":
        await query.edit_message_text("📝 Send your *image prompt*.", parse_mode="Markdown")

    elif mode == "image2video":
        await query.edit_message_text("📸 Send an image first.")


# ----------------------------------------------------
# TEXT HANDLER
# ----------------------------------------------------
async def message_handler(update, context):
    user_id = update.message.chat_id
    text = update.message.text

    if user_id not in user_sessions:
        await update.message.reply_text("Please choose from menu using /start")
        return

    # Admin unlimited / Users limited to 2
    if user_id != ADMIN_ID:
        count = user_counts.get(user_id, 0)
        if count >= 2:
            await update.message.reply_text("⚠️ You reached *2 free generations*.\nContact admin for more.")
            return

    mode = user_sessions[user_id]["mode"]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))

    IMAGE_MODEL = "higgsfield-ai/soul/standard"
    VIDEO_MODEL = "higgsfield-ai/dop/standard"

    # ------------------------------
    # TEXT → IMAGE
    # ------------------------------
    if mode == "text2image":
        await update.message.reply_text("🎨 Generating your image…")

        payload = {"prompt": text}
        resp = hf.submit(IMAGE_MODEL, payload)
        req_id = resp["request_id"]
        result = hf.wait_for_result(req_id)

        if result.get("status") == "completed":
            await update.message.reply_photo(result["images"][0]["url"])
            if user_id != ADMIN_ID:
                user_counts[user_id] = user_counts.get(user_id, 0) + 1
        else:
            await update.message.reply_text("❌ Failed to generate image.")


    # ------------------------------
    # IMAGE → VIDEO
    # ------------------------------
    elif mode == "image2video":
        if "image_url" not in user_sessions[user_id]:
            await update.message.reply_text("❗ Send an image first.")
            return

        image_url = user_sessions[user_id]["image_url"]

        await update.message.reply_text("🎬 Generating your video…")

        payload = {
            "image_url": image_url,
            "prompt": text,
            "duration": 5
        }

        resp = hf.submit(VIDEO_MODEL, payload)
        req_id = resp["request_id"]
        result = hf.wait_for_result(req_id)

        if result.get("status") == "completed":
            await update.message.reply_video(result["video"]["url"])
            if user_id != ADMIN_ID:
                user_counts[user_id] = user_counts.get(user_id, 0) + 1
        else:
            await update.message.reply_text("❌ Video generation failed.")


# ----------------------------------------------------
# PHOTO HANDLER
# ----------------------------------------------------
async def photo_handler(update, context):
    user_id = update.message.chat_id

    if user_id not in user_sessions or user_sessions[user_id]["mode"] != "image2video":
        await update.message.reply_text("Please choose Image → Video using /start")
        return

    # Download image
    file = await update.message.photo[-1].get_file()
    img_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(img_path)

    # Upload to Cloudflare R2 (public bucket)
    files = {"file": open(img_path, "rb")}
    r = requests.post("https://pub-8bf9b7d855d54c82a736b3d813276b48.r2.dev", files=files)

    if r.status_code != 200:
        await update.message.reply_text("❌ Failed to upload image.")
        return

    image_url = r.json().get("url")
    user_sessions[user_id]["image_url"] = image_url

    await update.message.reply_text("📌 Image saved.\nNow send your *video prompt*.")


# ----------------------------------------------------
# REGISTER HANDLERS
# ----------------------------------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

import os
import uuid
import requests
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

# =====================================================
# CONFIG
# =====================================================
ADMIN_ID = 7872634386
BUCKET_BASE = "https://pub-8bf9b7d855d54c82a736b3d813276b48.r2.dev/higgs-image"

HF_KEY = os.getenv("HF_KEY")
HF_SECRET = os.getenv("HF_SECRET")

user_sessions = {}
usage_count = {}

# =====================================================
# START
# =====================================================
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🖼 → 🎬 Image → Video", callback_data="image2video")],
    ]

    welcome = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "⚡ Create Images and Videos using official Higgsfield Cloud.\n\n"
        "📢 For advanced prompts, subscribe @HiggsMasterBot\n"
        "🧪 Free users: 2 generations\n"
        "👑 Admin: Unlimited\n\n"
        "Select an option below."
    )

    await update.message.reply_text(
        welcome, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =====================================================
# MENU BUTTON HANDLER
# =====================================================
async def button_handler(update, context):
    q = update.callback_query
    await q.answer()

    mode = q.data
    chat_id = q.message.chat_id

    user_sessions[chat_id] = {"mode": mode}

    if mode == "text2image":
        await q.edit_message_text("📝 Send your *image prompt*.", parse_mode="Markdown")

    elif mode == "image2video":
        await q.edit_message_text("📸 Send an image. Then send video prompt.")


# =====================================================
# LIMIT SYSTEM
# =====================================================
def check_limit(user_id):
    if user_id == ADMIN_ID:
        return True

    if user_id not in usage_count:
        usage_count[user_id] = 0

    return usage_count[user_id] < 2


def increase_limit(user_id):
    if user_id != ADMIN_ID:
        usage_count[user_id] += 1


# =====================================================
# R2 UPLOAD
# =====================================================
def upload_to_r2(local_path):
    file_name = f"{uuid.uuid4()}.jpg"
    url = f"{BUCKET_BASE}/{file_name}"

    headers = {
        "Content-Type": "application/octet-stream",
        "x-amz-acl": "public-read"
    }

    with open(local_path, "rb") as f:
        resp = requests.put(url, data=f, headers=headers)

    if resp.status_code in [200, 201]:
        return url

    print("R2 Upload Error:", resp.text)
    return None


# =====================================================
# TEXT HANDLER
# =====================================================
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    # Log to admin
    await context.bot.send_message(ADMIN_ID, f"User {chat_id} prompt: {text}")

    if chat_id not in user_sessions:
        await update.message.reply_text("Please select from menu using /start")
        return

    if not check_limit(chat_id):
        await update.message.reply_text("⚠️ Free limit reached. Subscribe @HiggsMasterBot")
        return

    mode = user_sessions[chat_id]["mode"]
    hf = HiggsfieldAPI(HF_KEY, HF_SECRET)

    IMAGE_MODEL = "higgsfield-ai/soul/standard"
    VIDEO_MODEL = "higgsfield-ai/dop/standard"

    loading = await update.message.reply_text("⏳ Generating… Please wait.")

    # --------------------------------------------------------
    # TEXT → IMAGE
    # --------------------------------------------------------
    if mode == "text2image":
        payload = {"prompt": text}

        resp = hf.submit(IMAGE_MODEL, payload)
        req = resp["request_id"]
        final = hf.wait_for_result(req)

        if final.get("status") == "completed":
            increase_limit(chat_id)
            await context.bot.delete_message(chat_id, loading.message_id)
            await update.message.reply_photo(final["images"][0]["url"])
        else:
            await update.message.reply_text("❌ Generation failed.")

    # --------------------------------------------------------
    # IMAGE → VIDEO
    # --------------------------------------------------------
    elif mode == "image2video":
        if "image" not in user_sessions[chat_id]:
            await update.message.reply_text("📸 Please send an image first.")
            return

        local_image = user_sessions[chat_id]["image"]

        # Upload to R2
        img_url = upload_to_r2(local_image)
        if not img_url:
            await update.message.reply_text("❌ Image upload failed.")
            return

        payload = {
            "image_url": img_url,
            "prompt": text,
            "duration": 5
        }

        resp = hf.submit(VIDEO_MODEL, payload)
        req = resp["request_id"]
        final = hf.wait_for_result(req)

        if final.get("status") == "completed":
            increase_limit(chat_id)
            await context.bot.delete_message(chat_id, loading.message_id)
            await update.message.reply_video(final["video"]["url"])
        else:
            await update.message.reply_text("❌ Video generation failed.")


# =====================================================
# PHOTO HANDLER
# =====================================================
async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        await update.message.reply_text("Select Image→Video first using /start")
        return

    file = await update.message.photo[-1].get_file()
    img_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(img_path)

    user_sessions[chat_id]["image"] = img_path

    # Log to admin
    await context.bot.send_message(ADMIN_ID, f"User {chat_id} uploaded an image.")

    await update.message.reply_text("📌 Image saved. Now send your video prompt.")


# =====================================================
# REGISTER HANDLERS
# =====================================================
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

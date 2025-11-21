import os
import asyncio
import boto3
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ApplicationBuilder,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from higgsfield_api import HiggsfieldAPI
import requests

# ---------------------------
# CLOUDLFARE R2 CONFIG
# ---------------------------
R2_ENDPOINT = "https://cf35bbda8be20eaa0b511c5171174ff2.r2.cloudflarestorage.com"
R2_BUCKET = "higgs-image"
R2_ACCESS_KEY = "6a1ffdbb0a5a5b9f8e94468a9cebab74"
R2_SECRET_KEY = "7949fc22df6c16062ece0f9b65be40d92d44c46d09f1b4fb4db8e00a534efa38"

s3 = boto3.client(
    "s3",
    endpoint_url=R2_ENDPOINT,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
)

# ---------------------------
# ADMIN + USER LIMITS
# ---------------------------
ADMIN_ID = 7872634386
user_usage = {}  # track generation count
MAX_GEN = 2       # normal user limit

# ---------------------------
# SESSION MEMORY
# ---------------------------
user_sessions = {}

# ---------------------------
# START
# ---------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🖼 → 🎬 Image → Video", callback_data="image2video")],
    ]

    msg = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "⚡ Powered by Cloudflare R2 hosting\n"
        "🧑‍💻 Bot by @honeyhoney44\n\n"
        "You have *2 free generations*. Admin has unlimited.\n"
        "Please select an option below."
    )

    await update.message.reply_text(
        msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------------------------
# BUTTON HANDLER
# ---------------------------
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    mode = query.data
    chat_id = query.message.chat_id

    user_sessions[chat_id] = {"mode": mode}

    if mode == "text2image":
        await query.edit_message_text("📝 Send your text prompt for Image Generation.")

    elif mode == "image2video":
        await query.edit_message_text("📸 Send an image first, then send your video prompt.")

# ---------------------------
# UPLOAD TO CLOUDFLARE R2
# ---------------------------
def upload_to_r2(local_path):
    file_name = os.path.basename(local_path)

    s3.upload_file(
        local_path,
        R2_BUCKET,
        file_name,
        ExtraArgs={"ContentType": "image/jpeg"}
    )

    return f"{R2_ENDPOINT}/{R2_BUCKET}/{file_name}"

# ---------------------------
# TEXT HANDLER
# ---------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    # Log every prompt to admin
    if chat_id != ADMIN_ID:
        await context.bot.send_message(
            ADMIN_ID, f"📩 User `{chat_id}` prompt:\n{text}"
        )

    # User must pick menu
    if chat_id not in user_sessions:
        await update.message.reply_text("Please choose from menu using /start")
        return

    # Limit for normal users
    if chat_id != ADMIN_ID:
        user_usage.setdefault(chat_id, 0)
        if user_usage[chat_id] >= MAX_GEN:
            await update.message.reply_text("❌ You used your 2 free generations. Contact admin for more.")
            return

    mode = user_sessions[chat_id]["mode"]
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))

    IMAGE_MODEL = "higgsfield-ai/soul/standard"
    VIDEO_MODEL = "higgsfield-ai/dop/standard"

    # ------------------------------
    # TEXT → IMAGE
    # ------------------------------
    if mode == "text2image":
        payload = {"prompt": text}
        resp = hf.submit(IMAGE_MODEL, payload)
        req_id = resp["request_id"]

        final = hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            user_usage[chat_id] = user_usage.get(chat_id, 0) + 1
            await update.message.reply_photo(final["images"][0]["url"])
        else:
            await update.message.reply_text("❌ Failed to generate image.")

    # ------------------------------
    # IMAGE → VIDEO
    # ------------------------------
    elif mode == "image2video":
        if "image" not in user_sessions[chat_id]:
            await update.message.reply_text("📸 Send an image first.")
            return

        local_path = user_sessions[chat_id]["image"]

        # upload to R2
        try:
            image_url = upload_to_r2(local_path)
        except Exception as e:
            await update.message.reply_text("❌ Failed to upload image.")
            return

        payload = {
            "image_url": image_url,
            "prompt": text,
            "duration": 5
        }

        resp = hf.submit(VIDEO_MODEL, payload)
        req_id = resp["request_id"]

        final = hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            user_usage[chat_id] = user_usage.get(chat_id, 0) + 1
            await update.message.reply_video(final["video"]["url"])
        else:
            await update.message.reply_text("❌ Video generation failed.")

# ---------------------------
# PHOTO HANDLER
# ---------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        await update.message.reply_text("Select Image→Video first using /start.")
        return

    file = await update.message.photo[-1].get_file()
    img_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(img_path)

    user_sessions[chat_id]["image"] = img_path
    await update.message.reply_text("📌 Image saved. Now send your video prompt.")

# ---------------------------
# REGISTER HANDLERS
# ---------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

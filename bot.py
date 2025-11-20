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
import requests

# GLOBAL SESSION MEMORY
user_sessions = {}

# ---------------------------
# START COMMAND
# ---------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🖼 → 🎬 Image → Video (DoP)", callback_data="image2video")],
    ]

    welcome_text = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "Create images & videos using official Higgsfield Cloud.\n\n"
        "✨ Bot by @honeyhoney44\n"
        "Select an option below."
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
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
        await query.edit_message_text("📝 Send your *text prompt* for Image Generation.", parse_mode="Markdown")

    elif mode == "image2video":
        await query.edit_message_text("📸 Send an image first. Then send a video prompt.")

# ----------------------------------------------------
#  STEP-BY-STEP LOADING
# ----------------------------------------------------
async def loading_animation(context, chat_id, message_id, stop_event):
    frames = [
        "⏳ Step 1: Request sent…",
        "🔄 Step 2: Model processing…",
        "🎬 Step 3: Rendering…",
        "✨ Step 4: Finalizing…"
    ]
    i = 0
    while not stop_event.is_set():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=frames[i % len(frames)]
            )
        except:
            pass
        i += 1
        await asyncio.sleep(4)

# ---------------------------
# TEXT HANDLER
# ---------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    if chat_id not in user_sessions:
        await update.message.reply_text("Please choose from the menu using /start")
        return

    mode = user_sessions[chat_id]["mode"]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))

    IMAGE_MODEL = "higgsfield-ai/soul/standard"
    VIDEO_MODEL = "higgsfield-ai/dop/preview"  # ✅ FIXED MODEL

    # Start loading animation
    loading_msg = await update.message.reply_text("⏳ Loading…")
    stop_event = asyncio.Event()

    context.application.create_task(
        loading_animation(context, chat_id, loading_msg.message_id, stop_event)
    )

    # ------------------------------
    # TEXT → IMAGE
    # ------------------------------
    if mode == "text2image":
        payload = {"prompt": text}

        resp = hf.submit(IMAGE_MODEL, payload)
        req_id = resp["request_id"]

        final = hf.wait_for_result(req_id)
        stop_event.set()

        if final.get("status") == "completed":
            await update.message.reply_photo(final["images"][0]["url"])
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")

    # ------------------------------
    # IMAGE → VIDEO (DoP)
    # ------------------------------
    elif mode == "image2video":
        if "image" not in user_sessions[chat_id]:
            stop_event.set()
            await update.message.reply_text("📸 Please send an image first.")
            return

        image_path = user_sessions[chat_id]["image"]

        # Upload image to free hosting
        with open(image_path, "rb") as f:
            upload = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": f})

        image_url = upload.json()["data"]["url"].replace("/download", "")

        payload = {
            "image_url": image_url,
            "prompt": text,
            "duration": 5
        }

        resp = hf.submit(VIDEO_MODEL, payload)
        req_id = resp["request_id"]

        final = hf.wait_for_result(req_id)
        stop_event.set()

        if final.get("status") == "completed":
            await update.message.reply_video(final["video"]["url"])
        else:
            await update.message.reply_text(f"❌ Video generation failed: {final.get('status')}")

# ---------------------------
# PHOTO HANDLER
# ---------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        await update.message.reply_text("Select Image→Video first using /start")
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

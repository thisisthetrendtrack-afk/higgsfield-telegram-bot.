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

# GLOBAL MEMORY
user_sessions = {}

# ---------------------------
# START COMMAND
# ---------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 → 🎬 Image → Video (DoP Preview)", callback_data="image2video")],
    ]

    welcome_text = (
        "🤖 *Higgsfield Image → Video Bot*\n"
        "Uses official DoP Preview Model.\n\n"
        "✨ Bot by @honeyhoney44\n"
        "Send an image to start."
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

    if mode == "image2video":
        await query.edit_message_text("📸 Send an image first.")


# ---------------------------
# LOADING ANIMATION
# ---------------------------
async def loading_animation(context, chat_id, msg_id, stop_event):
    frames = [
        "⏳ Step 1: Uploading…",
        "🔄 Step 2: Processing…",
        "🎬 Step 3: Rendering Video…",
        "✨ Step 4: Finalizing…"
    ]
    i = 0
    while not stop_event.is_set():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id, text=frames[i % len(frames)]
            )
        except:
            pass
        i += 1
        await asyncio.sleep(4)

# ---------------------------
# PHOTO HANDLER
# ---------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        await update.message.reply_text("Choose Image→Video using /start first")
        return

    file = await update.message.photo[-1].get_file()
    local_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(local_path)

    # Convert to stable URL
    file_url = f"https://files.catbox.moe/{file.file_id}.jpg"

    # Upload to catbox
    with open(local_path, "rb") as f:
        upload = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": f},
        )
        file_url = upload.text.strip()

    user_sessions[chat_id]["image_url"] = file_url

    await update.message.reply_text(
        "📌 Image saved!\nNow send your *video motion prompt*."
    )

# ---------------------------
# TEXT HANDLER
# ---------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    if (
        chat_id not in user_sessions
        or "image_url" not in user_sessions[chat_id]
        or user_sessions[chat_id]["mode"] != "image2video"
    ):
        return

    image_url = user_sessions[chat_id]["image_url"]

    loading_msg = await update.message.reply_text("⏳ Starting…")
    stop_event = asyncio.Event()
    context.application.create_task(
        loading_animation(context, chat_id, loading_msg.message_id, stop_event)
    )

    # API client
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    MODEL = "higgsfield-ai/dop/preview"

    payload = {
        "image_url": image_url,
        "prompt": text,
        "duration": 5
    }

    resp = hf.submit(MODEL, payload)
    req_id = resp["request_id"]

    final = hf.wait_for_result(req_id)
    stop_event.set()

    if final.get("status") == "completed":
        await update.message.reply_video(final["video"]["url"])
    else:
        await update.message.reply_text(f"❌ Failed: {final.get('status')}")


# ---------------------------
# REGISTER HANDLERS
# ---------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

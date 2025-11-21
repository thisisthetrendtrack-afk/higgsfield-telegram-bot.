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

# ---------------------------
# ADMIN + LIMIT CONFIG
# ---------------------------
ADMIN_ID = 7872634386
GEN_LIMIT = 2
user_usage = {}      # tracks how many generations user did
LOG_CHAT = ADMIN_ID  # log all prompts to admin

# GLOBAL SESSION MEMORY
user_sessions = {}

# ---------------------------
# START COMMAND
# ---------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🖼 → 🎬 Image → Video", callback_data="image2video")],
    ]

    welcome_text = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "Create images & videos using official Higgsfield Cloud.\n\n"
        "✨ Bot by @honeyhoney44\n"
        "For prompts subscribe: @HiggsMasterBot\n\n"
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
        await query.edit_message_text("📝 Send your *text prompt*.", parse_mode="Markdown")

    elif mode == "image2video":
        await query.edit_message_text("📸 Send an image first. Then send a video prompt.")


# ---------------------------
# LOADING ANIMATION
# ---------------------------
async def loading_animation(context, chat_id, message_id, stop_event):
    frames = [
        "⏳ Generating…",
        "🔄 Processing…",
        "✨ Almost ready…"
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
        await asyncio.sleep(3)


# ---------------------------
# UPLOAD TO IMGBB
# ---------------------------
def upload_to_imgbb(path):
    API_KEY = os.getenv("IMGBB_KEY")  # you added this already
    with open(path, "rb") as f:
        res = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": API_KEY},
            files={"image": f}
        )
    return res.json()["data"]["url"]


# ---------------------------
# TEXT HANDLER
# ---------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    text = update.message.text

    # Log prompt to admin
    await context.bot.send_message(LOG_CHAT, f"User {user_id} prompt: {text}")

    if chat_id not in user_sessions:
        await update.message.reply_text("Please choose from /start menu.")
        return

    # LIMIT CHECK
    if user_id != ADMIN_ID:
        count = user_usage.get(user_id, 0)
        if count >= GEN_LIMIT:
            await update.message.reply_text("⚠️ You reached your free 2-generation limit.\nSubscribe @HiggsMasterBot for unlimited access.")
            return

    mode = user_sessions[chat_id]["mode"]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))

    IMAGE_MODEL = "higgsfield-ai/soul/standard"
    VIDEO_MODEL = "higgsfield-ai/dop/standard"

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

        if final["status"] == "completed":
            await update.message.reply_photo(final["images"][0]["url"])

            if user_id != ADMIN_ID:
                user_usage[user_id] = user_usage.get(user_id, 0) + 1

        else:
            await update.message.reply_text("❌ Failed.")


    # ------------------------------
    # IMAGE → VIDEO
    # ------------------------------
    elif mode == "image2video":
        if "image" not in user_sessions[chat_id]:
            stop_event.set()
            await update.message.reply_text("📸 Send an image first.")
            return

        image_path = user_sessions[chat_id]["image"]

        # Upload image to IMGBB
        image_url = upload_to_imgbb(image_path)

        payload = {
            "image_url": image_url,
            "prompt": text,
            "duration": 5
        }

        resp = hf.submit(VIDEO_MODEL, payload)
        req_id = resp["request_id"]

        final = hf.wait_for_result(req_id)
        stop_event.set()

        if final["status"] == "completed":
            await update.message.reply_video(final["video"]["url"])

            if user_id != ADMIN_ID:
                user_usage[user_id] = user_usage.get(user_id, 0) + 1

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

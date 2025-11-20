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

# SESSION MEMORY
user_sessions = {}


# ----------------------------------------------------
# START COMMAND
# ----------------------------------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🎬 Text → Video (Soul)", callback_data="text2video")],
        [InlineKeyboardButton("🖼 → 🎬 Image → Video", callback_data="image2video")],
        [InlineKeyboardButton("👤 Characters", callback_data="characters")],
        [InlineKeyboardButton("💫 Motions", callback_data="motions")],
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


# ----------------------------------------------------
# HELP
# ----------------------------------------------------
async def help_cmd(update, context):
    await update.message.reply_text(
        "📌 Commands:\n"
        "/text2image – Text to Image\n"
        "/text2video – Text to Video (Soul)\n"
        "/image2video – Image to Video\n"
        "/characters – Character creation\n"
        "/motions – Motion generation\n"
        "/status <id> – Request status\n"
        "/cancel <id> – Cancel request"
    )


# ----------------------------------------------------
# MENU BUTTONS
# ----------------------------------------------------
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    mode = query.data
    chat_id = query.message.chat_id
    user_sessions[chat_id] = {"mode": mode}

    text_map = {
        "text2image": "📝 Send your *text prompt* for Image Generation.",
        "text2video": "📝 Send your *text prompt* for Soul Video Generation.",
        "characters": "📝 Send your *character prompt*.",
        "motions": "📝 Send your *motion prompt*.",
        "image2video": "📸 Send an image first. Then send a prompt.",
    }

    await query.edit_message_text(text_map[mode], parse_mode="Markdown")


# ----------------------------------------------------
# LOADING ANIMATION
# ----------------------------------------------------
async def loading_animation(context, chat_id, message_id, stop_event):
    frames = ["⏳ Loading…", "🔄 Generating…", "🔃 Almost done…"]
    i = 0
    while not stop_event.is_set():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=frames[i % 3]
            )
        except:
            pass
        i += 1
        await asyncio.sleep(4)


# ----------------------------------------------------
# TEXT MESSAGE HANDLER
# ----------------------------------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    if chat_id not in user_sessions:
        await update.message.reply_text("Please choose using /start")
        return

    mode = user_sessions[chat_id]["mode"]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))

    IMAGE_MODEL = "higgsfield-ai/soul/standard"
    VIDEO_MODEL = "higgsfield-ai/soul/video"

    # Start loading
    loading_msg = await update.message.reply_text("⏳ Loading…")
    stop_event = asyncio.Event()
    context.application.create_task(
        loading_animation(context, chat_id, loading_msg.message_id, stop_event)
    )

    # -----------------------------------------
    # TEXT → IMAGE
    # -----------------------------------------
    if mode == "text2image":
        resp = hf.submit(IMAGE_MODEL, {"prompt": text})
        req_id = resp["request_id"]
        final = hf.wait_for_result(req_id)
        stop_event.set()

        if final.get("status") == "completed":
            await update.message.reply_photo(final["images"][0]["url"])
        else:
            await update.message.reply_text("❌ Failed.")

    # -----------------------------------------
    # TEXT → VIDEO (correct model)
    # -----------------------------------------
    elif mode == "text2video":
        resp = hf.submit(VIDEO_MODEL, {"prompt": text})
        req_id = resp["request_id"]
        final = hf.wait_for_result(req_id)
        stop_event.set()

        if final.get("status") == "completed" and "video" in final:
            await update.message.reply_video(final["video"]["url"])
        else:
            await update.message.reply_text("❌ Video generation failed. Try simpler prompt.")

    # -----------------------------------------
    # CHARACTERS
    # -----------------------------------------
    elif mode == "characters":
        resp = hf.submit(IMAGE_MODEL, {"prompt": text})
        req_id = resp["request_id"]
        final = hf.wait_for_result(req_id)
        stop_event.set()

        if final.get("status") == "completed":
            await update.message.reply_photo(final["images"][0]["url"])
        else:
            await update.message.reply_text("❌ Failed.")

    # -----------------------------------------
    # MOTIONS
    # -----------------------------------------
    elif mode == "motions":
        resp = hf.submit(VIDEO_MODEL, {"prompt": text})
        req_id = resp["request_id"]
        final = hf.wait_for_result(req_id)
        stop_event.set()

        if final.get("status") == "completed" and "video" in final:
            await update.message.reply_video(final["video"]["url"])
        else:
            await update.message.reply_text("❌ Failed.")


# ----------------------------------------------------
# PHOTO HANDLER (Image → Video)
# ----------------------------------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        await update.message.reply_text("Select Image → Video from menu first.")
        return

    file = await update.message.photo[-1].get_file()
    img_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(img_path)

    user_sessions[chat_id]["image"] = img_path
    await update.message.reply_text("📌 Image received. Now send your prompt.")


# ----------------------------------------------------
# STATUS
# ----------------------------------------------------
async def status_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /status <id>")
        return

    req_id = context.args[0]
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    data = hf.get_status(req_id)

    await update.message.reply_text(f"📊 Status: {data['status']}")


# ----------------------------------------------------
# CANCEL
# ----------------------------------------------------
async def cancel_cmd(update, context):
    if not context.args:
        await update.message.reply_text("Usage: /cancel <id>")
        return

    req_id = context.args[0]
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    url = f"https://platform.higgsfield.ai/requests/{req_id}/cancel"

    resp = requests.post(url, headers=hf.headers)
    await update.message.reply_text(f"🛑 Cancel response: {resp.status_code}")


# ----------------------------------------------------
# REGISTER HANDLERS
# ----------------------------------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

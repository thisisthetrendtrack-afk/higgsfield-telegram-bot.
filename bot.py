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

# ---------------------------
# HELP COMMAND
# ---------------------------
async def help_cmd(update, context):
    await update.message.reply_text(
        "📌 Available Commands:\n\n"
        "/text2image – Generate images from text\n"
        "/text2video – Generate videos from text (Soul)\n"
        "/image2video – Generate video from uploaded image\n"
        "/characters – Create consistent characters\n"
        "/motions – Apply motions\n"
        "/status <id> – Check generation status\n"
        "/cancel <id> – Cancel queued generation"
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

    mode_texts = {
        "text2image": "📝 Send your *text prompt* for Image Generation.",
        "text2video": "📝 Send your *text prompt* for Soul Video Generation.",
        "characters": "📝 Send your *prompt* for Character Creation.",
        "motions": "📝 Send your prompt for Motion Generation.",
        "image2video": "📸 Send an image first. Then send a prompt."
    }

    await query.edit_message_text(
        mode_texts.get(mode, "Send your prompt."),
        parse_mode="Markdown"
    )

# ---------------------------
# TEXT HANDLER
# ---------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    if chat_id not in user_sessions:
        await update.message.reply_text("Please choose from the menu using /start")
        return

    mode = user_sessions[chat_id].get("mode")

    # Initialize API client
    hf = HiggsfieldAPI(
        os.getenv("HF_KEY"),
        os.getenv("HF_SECRET")
    )

    MODEL = "higgsfield-ai/soul/standard"

    # IMAGE: TEXT → IMAGE
    if mode == "text2image":
        payload = {"prompt": text}
        resp = hf.submit(MODEL, payload)
        req_id = resp.get("request_id")

        await update.message.reply_text(
            f"🟦 Image generation started.\nRequest ID: `{req_id}`",
            parse_mode="Markdown"
        )
        await update.message.reply_text("🟡 Queued… please wait")

        final = hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            await update.message.reply_photo(final["images"][0]["url"])
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")
        return

    # VIDEO: TEXT → VIDEO
    elif mode == "text2video":
        payload = {"prompt": text}
        resp = hf.submit(MODEL, payload)
        req_id = resp.get("request_id")

        await update.message.reply_text(
            f"🎬 Video generation started.\nRequest ID: `{req_id}`",
            parse_mode="Markdown"
        )
        await update.message.reply_text("🟡 Queued… please wait")

        final = hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            await update.message.reply_video(final["video"]["url"])
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")
        return

    # CHARACTERS
    elif mode == "characters":
        payload = {"prompt": text}
        resp = hf.submit(MODEL, payload)
        req_id = resp.get("request_id")

        await update.message.reply_text(
            f"👤 Character generation started.\nID: `{req_id}`",
            parse_mode="Markdown"
        )
        await update.message.reply_text("🟡 Queued… please wait")

        final = hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            await update.message.reply_photo(final["images"][0]["url"])
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")
        return

    # MOTIONS
    elif mode == "motions":
        payload = {"prompt": text}
        resp = hf.submit(MODEL, payload)
        req_id = resp.get("request_id")

        await update.message.reply_text(
            f"💫 Motion generation started.\nID: `{req_id}`",
            parse_mode="Markdown"
        )
        await update.message.reply_text("🟡 Queued… please wait")

        final = hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            await update.message.reply_video(final["video"]["url"])
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")
        return

# ---------------------------
# PHOTO HANDLER
# ---------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        await update.message.reply_text("Please select Image → Video from /start first.")
        return

    file = await update.message.photo[-1].get_file()
    img_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(img_path)

    user_sessions[chat_id]["image"] = img_path

    await update.message.reply_text("📌 Image saved. Now send your text prompt.")

# ---------------------------
# STATUS COMMAND
# ---------------------------
async def status_cmd(update, context):
    if not context.args:
        return await update.message.reply_text("Usage: /status <request_id>")

    req_id = context.args[0]
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    data = hf.get_status(req_id)

    await update.message.reply_text(f"📊 Status: {data.get('status')}")

# ---------------------------
# CANCEL COMMAND
# ---------------------------
async def cancel_cmd(update, context):
    if not context.args:
        return await update.message.reply_text("Usage: /cancel <request_id>")

    req_id = context.args[0]
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))

    url = f"https://platform.higgsfield.ai/requests/{req_id}/cancel"
    resp = requests.post(url, headers=hf.headers)

    await update.message.reply_text(f"🛑 Cancel response: {resp.status_code}")

# ---------------------------
# REGISTER HANDLERS
# ---------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

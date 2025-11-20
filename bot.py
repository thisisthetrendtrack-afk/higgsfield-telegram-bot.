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

    if mode == "text2image":
        await query.edit_message_text("📝 Send your text prompt for Image Generation.", parse_mode="Markdown")

    elif mode == "text2video":
        await query.edit_message_text("📝 Send your text prompt for Soul Video Generation.", parse_mode="Markdown")

    elif mode == "characters":
        await query.edit_message_text("📝 Send your character prompt.", parse_mode="Markdown")

    elif mode == "motions":
        await query.edit_message_text("📝 Send your motion prompt.", parse_mode="Markdown")

    elif mode == "image2video":
        await query.edit_message_text("📸 Send an image first. Then send a prompt.")


# ---------------------------
# MESSAGE HANDLER (text)
# ---------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    if chat_id not in user_sessions:
        await update.message.reply_text("Please choose an option using /start")
        return

    mode = user_sessions[chat_id].get("mode")

    hf = HiggsfieldAPI(
        os.getenv("HF_KEY"),
        os.getenv("HF_SECRET")
    )

    MODEL = "higgsfield-ai/soul/standard"

    # TEXT → IMAGE
    if mode == "text2image":
        payload = {"prompt": text}

        resp = hf.submit(MODEL, payload)
        req_id = resp["request_id"]

        await update.message.reply_text(
            f"🟦 Image generation started.\nRequest ID: `{req_id}`",
            parse_mode="Markdown"
        )

        final = hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            await update.message.reply_photo(final["images"][0]["url"])
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")

    # TEXT → VIDEO
    elif mode == "text2video":
        payload = {"prompt": text}

        resp = hf.submit(MODEL, payload)
        req_id = resp["request_id"]

        await update.message.reply_text(
            f"🎬 Video generation started.\nRequest ID: `{req_id}`",
            parse_mode="Markdown"
        )

        final = hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            await update.message.reply_video(final["video"]["url"])
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")

    # CHARACTERS
    elif mode == "characters":
        payload = {"prompt": text}

        resp = hf.submit(MODEL, payload)
        req_id = resp["request_id"]

        await update.message.reply_text(
            f"👤 Character creation started.\nID: `{req_id}`",
            parse_mode="Markdown"
        )

        final = hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            await update.message.reply_photo(final["images"][0]["url"])
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")

    # MOTIONS
    elif mode == "motions":
        payload = {"prompt": text}

        resp = hf.submit(MODEL, payload)
        req_id = resp["request_id"]

        await update.message.reply_text(
            f"💫 Motion generation started.\nID: `{req_id}`",
            parse_mode="Markdown"
        )

        final = hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            await update.message.reply_video(final["video"]["url"])
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")


# ---------------------------
# PHOTO (image → video)
# ---------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        return await update.message.reply_text("Pick Image → Video first using /start")

    file = await update.message.photo[-1].get_file()
    path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(path)

    user_sessions[chat_id]["image"] = path

    await update.message.reply_text("📌 Image received. Now send your video prompt.")


# ---------------------------
# STATUS / CANCEL
# ---------------------------
async def status_cmd(update, context):
    if len(context.args) == 0:
        return await update.message.reply_text("Usage: /status <request_id>")

    req_id = context.args[0]
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    data = hf.get_status(req_id)

    await update.message.reply_text(f"📊 Status: {data['status']}")


async def cancel_cmd(update, context):
    if len(context.args) == 0:
        return await update.message.reply_text("Usage: /cancel <request_id>")

    req_id = context.args[0]
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))

    url = f"https://platform.higgsfield.ai/requests/{req_id}/cancel"
    resp = requests.post(url, headers=hf.headers)

    await update.message.reply_text(f"🛑 Cancel response: {resp.status_code}")


# ---------------------------
# REGISTER
# ---------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

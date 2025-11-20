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


# GLOBAL STATE STORAGE
user_sessions = {}


# ---------------------------
# TELEGRAM BOT MENU COMMANDS
# ---------------------------

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🎬 Text → Video (Soul)", callback_data="text2video")],
        [InlineKeyboardButton("🏞 Image → Video (DoP)", callback_data="image2video")],
    ]

    welcome_text = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "Create images and videos using official Higgsfield Cloud.\n\n"
        "✨ Bot by @honeyhoney44\n"
        "Select an option below."
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def help_cmd(update, context):
    await update.message.reply_text(
        "📌 Commands:\n"
        "/text2image – Generate images\n"
        "/text2video – Generate videos (Soul)\n"
        "/image2video – Convert image to video (DoP)\n"
        "/status <id> – Check status\n"
        "/cancel <id> – Cancel request"
    )


# ---------------------------
# INLINE BUTTON HANDLER
# ---------------------------

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    choice = query.data
    chat_id = query.message.chat_id

    user_sessions[chat_id] = {"mode": choice}

    if choice == "text2image":
        await query.edit_message_text("📝 Send your *text prompt* for Image Generation.", parse_mode="Markdown")

    elif choice == "text2video":
        await query.edit_message_text("📝 Send your *text prompt* for Soul Video Generation.", parse_mode="Markdown")

    elif choice == "image2video":
        await query.edit_message_text("📸 Send an image first. Then send a prompt.")


# ---------------------------
# MESSAGE HANDLER (TEXT)
# ---------------------------

async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    if chat_id not in user_sessions:
        await update.message.reply_text("Please choose from menu using /start")
        return

    mode = user_sessions[chat_id].get("mode")

    hf = HiggsfieldAPI(
        os.getenv("HF_KEY"),
        os.getenv("HF_SECRET")
    )

    # TEXT → IMAGE
    if mode == "text2image":
        payload = {"prompt": text}
        resp = hf.submit("v1/image", payload)
        request_id = resp["job_set_id"]

        await update.message.reply_text(f"🟦 Image generation started.\nID: `{request_id}`", parse_mode="Markdown")

        final = hf.wait_for_result(request_id)

        if final["status"] == "completed":
            url = final["result"][0]["url"]
            await update.message.reply_photo(url)
        else:
            await update.message.reply_text("❌ Failed")

    # TEXT → VIDEO (SOUL)
    elif mode == "text2video":
        payload = {"prompt": text}
        resp = hf.submit("v1/video/soul", payload)
        request_id = resp["job_set_id"]

        await update.message.reply_text(f"🎬 Video generation started.\nID: `{request_id}`", parse_mode="Markdown")

        final = hf.wait_for_result(request_id)

        if final["status"] == "completed":
            url = final["result"]["url"]
            await update.message.reply_video(url)
        else:
            await update.message.reply_text("❌ Failed")

    # CHARACTERS REMOVED — NOT IN API


# ---------------------------
# PHOTO HANDLER
# ---------------------------

async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        await update.message.reply_text("To use Image → Video, click /start and select Image2Video.")
        return

    file = await update.message.photo[-1].get_file()
    img_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(img_path)

    user_sessions[chat_id]["image"] = img_path

    await update.message.reply_text("📌 Image received. Now send your prompt.")


# ---------------------------
# STATUS + CANCEL
# ---------------------------

async def status_cmd(update, context):
    if len(context.args) == 0:
        return await update.message.reply_text("Usage: /status <id>")

    request_id = context.args[0]
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    data = hf.get_status(request_id)

    await update.message.reply_text(f"📊 Status: {data['status']}")


def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

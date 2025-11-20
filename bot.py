import os
import asyncio
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from higgsfield_api import HiggsfieldAPI


# STORE USER STATE
user_sessions = {}


# ---------------------------
# START MESSAGE
# ---------------------------

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🎬 Text → Video (Soul)", callback_data="text2video")],
        [InlineKeyboardButton("🏞 Image → Video (DoP)", callback_data="image2video")],
    ]

    msg = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "Create images and videos using official Higgsfield Cloud.\n\n"
        "✨ Bot by @honeyhoney44\n"
        "Select an option below."
    )

    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ---------------------------
# HELP COMMAND
# ---------------------------

async def help_cmd(update, context):
    await update.message.reply_text(
        "📌 Commands:\n"
        "/text2image – Generate images\n"
        "/text2video – Soul video\n"
        "/image2video – Image to video\n"
        "/status <id> – Check status"
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
        await query.edit_message_text("📝 Send your *text prompt* for Image generation.", parse_mode="Markdown")

    elif mode == "text2video":
        await query.edit_message_text("📝 Send your *text prompt* for Soul video.", parse_mode="Markdown")

    elif mode == "image2video":
        await query.edit_message_text("📸 Send an image first, then send your prompt.")


# ---------------------------
# TEXT HANDLER
# ---------------------------

async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    if chat_id not in user_sessions:
        return await update.message.reply_text("Please choose an option using /start")

    mode = user_sessions[chat_id]["mode"]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))

    # --------------------- TEXT → IMAGE ---------------------
    if mode == "text2image":
        payload = {"prompt": text}

        resp = hf.submit("higgsfield-ai/image/standard", payload)
        request_id = resp["request_id"]

        await update.message.reply_text(
            f"🟦 Image generation started.\nRequest ID: `{request_id}`",
            parse_mode="Markdown",
        )

        final = hf.wait_for_result(request_id)

        if final["status"] == "completed":
            url = final["images"][0]["url"]
            await update.message.reply_photo(url)
        else:
            await update.message.reply_text(f"❌ Failed: {final['status']}")

    # --------------------- TEXT → VIDEO (SOUL) ---------------------
    elif mode == "text2video":
        payload = {"prompt": text}

        resp = hf.submit("higgsfield-ai/soul/standard", payload)
        request_id = resp["request_id"]

        await update.message.reply_text(
            f"🎬 Video generation started.\nRequest ID: `{request_id}`",
            parse_mode="Markdown",
        )

        final = hf.wait_for_result(request_id)

        if final["status"] == "completed":
            url = final["video"]["url"]
            await update.message.reply_video(url)
        else:
            await update.message.reply_text(f"❌ Failed: {final['status']}")


# ---------------------------
# PHOTO HANDLER (IMAGE → VIDEO)
# ---------------------------

async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        return await update.message.reply_text("Select Image → Video from /start first.")

    file = await update.message.photo[-1].get_file()
    img_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(img_path)

    user_sessions[chat_id]["image"] = img_path

    await update.message.reply_text("📌 Image received. Now send your prompt.")


# ---------------------------
# STATUS
# ---------------------------

async def status_cmd(update, context):
    if len(context.args) == 0:
        return await update.message.reply_text("Usage: /status <request_id>")

    request_id = context.args[0]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    data = hf.get_status(request_id)

    await update.message.reply_text(f"📊 Status: {data['status']}")


# ---------------------------
# REGISTER HANDLERS
# ---------------------------

def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

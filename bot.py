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


# GLOBAL STATE STORAGE (very simple)
user_sessions = {}


# ---------------------------
# TELEGRAM BOT MENU COMMANDS
# ---------------------------

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🎬 Text → Video (Soul)", callback_data="text2video")],
        [InlineKeyboardButton("🖼 → 🎬 Image → Video (DoP)", callback_data="image2video")],
        [InlineKeyboardButton("👤 Characters", callback_data="characters")],
        [InlineKeyboardButton("💫 Motions", callback_data="motions")],
    ]

    await update.message.reply_text(
        "🤖 *Welcome to Higgsfield Bot*\nSelect an option below.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


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
# INLINE BUTTON HANDLER
# ---------------------------

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    choice = query.data
    chat_id = query.message.chat_id

    user_sessions[chat_id] = {"mode": choice}

    # Ask for further input depending on choice
    if choice == "text2image":
        await query.edit_message_text("📝 Send your *text prompt* for Image Generation.", parse_mode="Markdown")

    elif choice == "text2video":
        await query.edit_message_text("📝 Send your *text prompt* for Soul Video Generation.", parse_mode="Markdown")

    elif choice == "characters":
        await query.edit_message_text("📝 Send your *prompt* for Character Creation.", parse_mode="Markdown")

    elif choice == "motions":
        await query.edit_message_text("📝 Send your prompt for Motion Generation.", parse_mode="Markdown")

    elif choice == "image2video":
        await query.edit_message_text("📸 Send an image first. Then send a prompt.")

# ---------------------------
# MESSAGE HANDLER (TEXT)
# ---------------------------

async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    if chat_id not in user_sessions:
        await update.message.reply_text("Please choose from the menu using /start")
        return

    mode = user_sessions[chat_id].get("mode")

    # API CLIENT
    hf = HiggsfieldAPI(
        os.getenv("HF_KEY"),
        os.getenv("HF_SECRET")
    )

    # ------------------------------
    # 1. TEXT → IMAGE
    # ------------------------------
    if mode == "text2image":
        payload = {
            "prompt": text,
            "aspect_ratio": "16:9",
            "resolution": "720p"
        }

        resp = hf.submit("higgsfield-ai/image/standard", payload)
        request_id = resp["request_id"]

        await update.message.reply_text(f"🟦 Image generation started.\nRequest ID: `{request_id}`", parse_mode="Markdown")

        final = hf.wait_for_result(request_id)

        if final["status"] == "completed":
            url = final["images"][0]["url"]
            await update.message.reply_photo(photo=url)
        else:
            await update.message.reply_text(f"❌ Failed: {final['status']}")

    # ------------------------------
    # 2. TEXT → VIDEO (SOUL)
    # ------------------------------
    elif mode == "text2video":
        payload = {
            "prompt": text,
            "aspect_ratio": "16:9",
            "resolution": "720p"
        }

        resp = hf.submit("higgsfield-ai/soul/standard", payload)
        request_id = resp["request_id"]

        await update.message.reply_text(f"🎬 Video generation started.\nRequest ID: `{request_id}`", parse_mode="Markdown")

        final = hf.wait_for_result(request_id)

        if final["status"] == "completed":
            url = final["video"]["url"]
            await update.message.reply_video(video=url)
        else:
            await update.message.reply_text(f"❌ Failed: {final['status']}")

    # ------------------------------
    # 3. CHARACTERS
    # ------------------------------
    elif mode == "characters":
        payload = {"prompt": text}

        resp = hf.submit("higgsfield-ai/characters/standard", payload)
        request_id = resp["request_id"]

        await update.message.reply_text(f"👤 Character creation started.\nID: `{request_id}`", parse_mode="Markdown")

        final = hf.wait_for_result(request_id)

        if final["status"] == "completed":
            url = final["images"][0]["url"]
            await update.message.reply_photo(photo=url)
        else:
            await update.message.reply_text(f"❌ Failed: {final['status']}")

    # ------------------------------
    # 4. MOTIONS
    # ------------------------------
    elif mode == "motions":
        payload = {"prompt": text}

        resp = hf.submit("higgsfield-ai/motions/standard", payload)
        request_id = resp["request_id"]

        await update.message.reply_text(f"💫 Motion generation started.\nID: `{request_id}`", parse_mode="Markdown")

        final = hf.wait_for_result(request_id)

        if final["status"] == "completed":
            url = final["video"]["url"]
            await update.message.reply_video(video=url)
        else:
            await update.message.reply_text(f"❌ Failed: {final['status']}")

# ---------------------------
# PHOTO HANDLER (for image2video)
# ---------------------------

async def photo_handler(update, context):
    chat_id = update.message.chat_id

    if chat_id not in user_sessions or user_sessions[chat_id]["mode"] != "image2video":
        await update.message.reply_text("To use Image → Video, click /start and select Image2Video first.")
        return

    # Download file
    file = await update.message.photo[-1].get_file()
    img_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(img_path)

    user_sessions[chat_id]["image"] = img_path

    await update.message.reply_text("📌 Image received. Now send a prompt.")

# ---------------------------
# STATUS + CANCEL COMMANDS
# ---------------------------

async def status_cmd(update, context):
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /status <request_id>")
        return

    request_id = context.args[0]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    data = hf.get_status(request_id)

    await update.message.reply_text(f"📊 Status: *{data['status']}*", parse_mode="Markdown")

async def cancel_cmd(update, context):
    if len(context.args) == 0:
        await update.message.reply_text("Usage: /cancel <request_id>")
        return

    request_id = context.args[0]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    url = f"https://platform.higgsfield.ai/requests/{request_id}/cancel"
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

import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

from utils import download_file
from higgsfield_api import HiggsfieldAPI

# Store user mode
user_mode = {}

# ---------------------------
# /start command
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["🎨 Stylize Image"],
        ["🖼 Text → Image"],
        ["🎬 Text → Video"],
        ["📊 Check Job Status"],
    ]

    await update.message.reply_text(
        "Choose an option:",
        reply_markup={"keyboard": keyboard, "resize_keyboard": True}
    )


# ---------------------------
# User selects a mode
# ---------------------------
async def mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mode = update.message.text
    user_mode[update.message.from_user.id] = mode
    await update.message.reply_text("Selected: " + mode + "\nNow send your input text or photo.")


# ---------------------------
# Handle ALL messages in selected mode
# ---------------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    api: HiggsfieldAPI = context.bot_data["hf"]
    user_id = update.message.from_user.id
    mode = user_mode.get(user_id)

    if not mode:
        await update.message.reply_text("Please choose an option using /start first.")
        return

    # ---------------------------
    # 1. TEXT → IMAGE
    # ---------------------------
    if mode.startswith("🖼"):
        prompt = update.message.text
        await update.message.reply_text("Creating image... wait...")

        job_id, data = await api.txt2img(prompt)
        await update.message.reply_text(f"Job created: {job_id}")
        return

    # ---------------------------
    # 2. TEXT → VIDEO
    # ---------------------------
    if mode.startswith("🎬"):
        prompt = update.message.text
        await update.message.reply_text("Creating video... wait...")

        job_id, data = await api.txt2video(prompt)
        await update.message.reply_text(f"Job created: {job_id}")
        return

    # ---------------------------
    # 3. CHECK JOB STATUS
    # ---------------------------
    if mode.startswith("📊"):
        job_id = update.message.text
        await update.message.reply_text("Checking status...")

        status = await api.get_job_status(job_id)
        await update.message.reply_text(str(status))
        return

    # ---------------------------
    # 4. STYLIZE IMAGE
    # ---------------------------
    if mode.startswith("🎨"):
        if not update.message.photo:
            await update.message.reply_text("Send a photo to stylize.")
            return

        file_id = update.message.photo[-1].file_id

        # USE UPDATED utils.py FUNCTION
        local_path = await download_file(context.bot, file_id)

        await update.message.reply_text("Stylizing your image...")

        job_id, data = await api.stylize(local_path)
        await update.message.reply_text(f"Job created: {job_id}")
        return


# ---------------------------
# Register all handlers (called from main.py)
# ---------------------------
def register_handlers(app, hf_api):
    app.bot_data["hf"] = hf_api

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^(🎨|🖼|🎬|📊).*"), mode_handler))
    app.add_handler(MessageHandler(filters.ALL, message_handler))

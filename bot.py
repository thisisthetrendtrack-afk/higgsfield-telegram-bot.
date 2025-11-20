import os
import logging
import asyncio
import requests
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    filters,
)
from telegram import Update
from higgsfield_api import HiggsfieldAPI

logger = logging.getLogger(__name__)

HF_KEY = os.getenv("HF_KEY")
HF_SECRET = os.getenv("HF_SECRET")

api = HiggsfieldAPI(HF_KEY, HF_SECRET)

# Track user’s uploaded images
user_state = {}


# -------------------------------------------------
# /start
# -------------------------------------------------
async def start(update: Update, context):
    await update.message.reply_text("Send me a photo to begin.")


# -------------------------------------------------
# PHOTO HANDLER
# -------------------------------------------------
async def handle_photo(update: Update, context):
    chat_id = update.message.chat_id
    file = await update.message.photo[-1].get_file()

    # IMPORTANT FIX:
    # Telegram gives a PUBLIC URL automatically
    image_url = file.file_path

    user_state[chat_id] = {"image_url": image_url}

    await update.message.reply_text("Image received. Now send your text prompt.")


# -------------------------------------------------
# PROMPT HANDLER
# -------------------------------------------------
async def handle_prompt(update: Update, context):
    chat_id = update.message.chat_id
    prompt = update.message.text

    if chat_id not in user_state:
        await update.message.reply_text("Send a photo first.")
        return

    image_url = user_state[chat_id]["image_url"]

    await update.message.reply_text("Submitting job to Higgsfield...")

    # STEP 1 — create job
    job_set_id, response = api.create_dop_job(image_url, prompt)

    if not job_set_id:
        await update.message.reply_text(f"Failed creating job.\nResponse: {response}")
        return

    await update.message.reply_text(f"Job created: {job_set_id}\nProcessing...")

    # STEP 2 — poll status
    for _ in range(45):
        try:
            status_data = api.get_job_status(job_set_id)
        except Exception as e:
            await update.message.reply_text(f"API error: {e}")
            return

        status = status_data.get("status")
        video_url = None

        # Many APIs put URL in different fields
        if "raw" in status_data and "url" in status_data["raw"]:
            video_url = status_data["raw"]["url"]

        if status == "completed" and video_url:
            await update.message.reply_video(video_url)
            return

        if status == "failed":
            await update.message.reply_text("Job failed. Try again.")
            return

        await asyncio.sleep(4)

    await update.message.reply_text("Still processing. Try again later.")


# -------------------------------------------------
# UNKNOWN CMD
# -------------------------------------------------
async def unknown(update: Update, context):
    await update.message.reply_text("Unknown command.")


# -------------------------------------------------
# Handler Registration (used in main.py)
# -------------------------------------------------
def register_handlers(app):

    app.add_handler(CommandHandler("start", start))

    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))

    app.add_handler(MessageHandler(filters.COMMAND, unknown))

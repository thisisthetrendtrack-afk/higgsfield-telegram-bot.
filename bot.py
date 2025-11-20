import os
import logging
import asyncio
import aiohttp
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
from higgsfield_api import HiggsfieldAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
HIGGS_API_KEY = os.getenv("HIGGS_API_KEY")

api = HiggsfieldAPI(api_key=HIGGS_API_KEY)

user_state = {}


# ---------------------------
# Simple file download helper
# ---------------------------
async def download_file(telegram_file):
    file_path = f"/tmp/{telegram_file.file_id}.jpg"
    await telegram_file.download_to_drive(file_path)
    return file_path


# ---------------------------
# Commands
# ---------------------------
async def start(update, context):
    await update.message.reply_text("Send me a photo to begin.")


async def handle_photo(update, context):
    chat_id = update.message.chat_id
    file = await update.message.photo[-1].get_file()
    
    image_path = await download_file(file)
    user_state[chat_id] = {"image": image_path}

    await update.message.reply_text("Image received. Now send your text prompt.")


async def handle_prompt(update, context):
    chat_id = update.message.chat_id
    prompt = update.message.text

    if chat_id not in user_state or "image" not in user_state[chat_id]:
        await update.message.reply_text("Send a photo first.")
        return

    image_path = user_state[chat_id]["image"]

    await update.message.reply_text("Creating DoP video... please wait.")

    # Create a DoP job
    job_set_id = await api.create_dop_job(
        image_path=image_path,
        prompt=prompt,
        model="dop-turbo",
        enhance_prompt=True
    )

    if not job_set_id:
        await update.message.reply_text("API Error. Try again.")
        return

    # Poll every 4 seconds
    for _ in range(45):
        status, video_url = await api.get_job_status(job_set_id)

        if status == "completed" and video_url:
            await update.message.reply_video(video=video_url)
            return

        await asyncio.sleep(4)

    await update.message.reply_text("Still processing… try again later.")


async def unknown(update, context):
    await update.message.reply_text("Send /start, a photo, or a text prompt.")


# ---------------------------
# Runner
# ---------------------------
def run_bot():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    app.run_polling()

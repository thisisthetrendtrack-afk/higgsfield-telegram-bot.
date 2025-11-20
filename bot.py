import os
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)
from higgsfield_api import create_dop_job, check_job_status
from utils import download_file

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")

user_state = {}

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

    if chat_id not in user_state or "image" not in user_state[chat_id]:
        await update.message.reply_text("Send a photo first.")
        return

    prompt = update.message.text
    image_path = user_state[chat_id]["image"]

    await update.message.reply_text("Creating DoP video... please wait.")

    job_id = await create_dop_job(image_path, prompt)
    if not job_id:
        await update.message.reply_text("API Error. Try again.")
        return

    # Poll every 4 seconds
    for _ in range(45):
        status, video_url = await check_job_status(job_id)
        if status == "completed":
            await update.message.reply_video(video=video_url)
            return
        await asyncio.sleep(4)

    await update.message.reply_text("Still processing. Try again later.")

async def unknown(update, context):
    await update.message.reply_text("Send /start, a photo, or a prompt.")

def run_bot():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    app.run_polling()

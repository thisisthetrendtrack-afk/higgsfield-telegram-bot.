import os
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from higgsfield_api import create_dop_job, poll_job_status

TOKEN = os.getenv("BOT_TOKEN")

user_state = {}  # chat_id: { "image_url": ... }

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    file = await update.message.photo[-1].get_file()
    image_url = file.file_path

    user_state[chat_id] = {"image_url": image_url}

    await update.message.reply_text("Image saved. Now send your text prompt.")

async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    prompt = update.message.text

    if chat_id not in user_state:
        await update.message.reply_text("Send a photo first.")
        return

    image_url = user_state[chat_id]["image_url"]

    await update.message.reply_text("Generating video... Please wait 10–40 seconds.")

    # Create Higgsfield job
    try:
        job_set_id = create_dop_job(image_url, prompt)
    except Exception as e:
        await update.message.reply_text(f"Error creating job: {e}")
        return

    # Poll job status
    while True:
        status, video_url = poll_job_status(job_set_id)

        if status == "completed":
            await update.message.reply_video(video_url)
            break

        if status in ["failed", "nsfw"]:
            await update.message.reply_text("Generation failed.")
            break

        time.sleep(4)

def run_bot():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable missing")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, handle_image))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))

    app.run_polling()

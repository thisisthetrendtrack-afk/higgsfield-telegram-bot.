import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

from higgsfield_api import txt2img, image2image, dop_video, check_status

# Per-user mode memory
user_mode = {}

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎨 Stylize Image", callback_data="i2i")],
        [InlineKeyboardButton("🖼 Text → Image", callback_data="txt2img")],
        [InlineKeyboardButton("🎬 Text → Video", callback_data="txt2vid")],
        [InlineKeyboardButton("📊 Check Job Status", callback_data="status")],
    ]

    await update.message.reply_text(
        "Choose an option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Handle menu choice
async def menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mode = query.data
    chat = query.message.chat_id

    user_mode[chat] = mode
    await query.edit_message_text(f"Selected: {mode}\nNow send input file or prompt.")

# Handle user message
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat_id
    text = update.message.text
    photo = update.message.photo

    if chat not in user_mode:
        return await update.message.reply_text("Use /start to choose an option.")

    mode = user_mode[chat]

    # TEXT → IMAGE
    if mode == "txt2img":
        await update.message.reply_text("Processing txt2img...")
        job = await txt2img(text)
        if not job:
            return await update.message.reply_text("API Error.")
        await poll_job(update, job)

    # IMAGE → IMAGE
    elif mode == "i2i":
        if not photo:
            return await update.message.reply_text("Send an image.")
        file_id = photo[-1].file_id
        image_url = await update.message.get_bot().get_file(file_id)
        await update.message.reply_text("Processing image2image...")
        job = await image2image(image_url.file_path)
        if not job:
            return await update.message.reply_text("API Error.")
        await poll_job(update, job)

    # TEXT → VIDEO (DOP)
    elif mode == "txt2vid":
        await update.message.reply_text("Creating DoP video… please wait.")
        job = await dop_video(prompt=text)
        if not job:
            return await update.message.reply_text("API Error.")
        await poll_job(update, job)

    # CHECK STATUS
    elif mode == "status":
        await update.message.reply_text("Checking job…")
        job = await check_status(text)
        if not job:
            return await update.message.reply_text("Job not found.")
        await poll_job(update, job)


# Poll job status
async def poll_job(update: Update, job):
    job_id = job.get("job_set_id")
    if not job_id:
        return await update.message.reply_text("Invalid job response.")

    await update.message.reply_text(f"Job ID: {job_id}\nPolling…")

    import asyncio
    while True:
        await asyncio.sleep(3)
        result = await check_status(job_id)

        status = result.get("status")
        if status == "completed":
            media_url = result["result"]["url"]
            await update.message.reply_text("Done!")
            return await update.message.reply_video(media_url)

        if status == "failed":
            return await update.message.reply_text("Job failed.")

# Build App
def run_bot():
    token = os.getenv("TELEGRAM_TOKEN")
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_button))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    print("BOT RUNNING...")
    app.run_polling()


if __name__ == "__main__":
    run_bot()

import os
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from higgsfield_api import txt2img, image2image, dop_video, check_status

user_mode = {}
user_input = {}

async def start(update, context):
    chat = update.message.chat_id
    user_mode.pop(chat, None)
    await update.message.reply_text(
        "Choose an option:\n"
        "🎨 /stylize\n"
        "🖼 /txt2img\n"
        "🎬 /txt2video\n"
        "📊 /status"
    )

async def stylize(update, context):
    user_mode[update.message.chat_id] = "stylize"
    await update.message.reply_text("Send image + prompt.")

async def txt2img_cmd(update, context):
    user_mode[update.message.chat_id] = "txt2img"
    await update.message.reply_text("Send your text prompt.")

async def txt2video(update, context):
    user_mode[update.message.chat_id] = "dop"
    await update.message.reply_text("Send an image first.")

async def status_cmd(update, context):
    user_mode[update.message.chat_id] = "status"
    await update.message.reply_text("Send job_id to check status.")

async def handle_photo(update, context):
    chat = update.message.chat_id
    if chat not in user_mode:
        return await update.message.reply_text("Select a mode using /start")

    file = await update.message.photo[-1].get_file()
    file_path = f"/tmp/{file.file_id}.jpg"
    await file.download_to_drive(file_path)

    user_input[chat] = file_path
    await update.message.reply_text("Image received. Now send your prompt.")

async def handle_text(update, context):
    chat = update.message.chat_id
    text = update.message.text

    if chat not in user_mode:
        return await update.message.reply_text("Choose an option using /start")

    mode = user_mode[chat]

    if mode == "txt2img":
        await update.message.reply_text("Processing txt2img...")

        job = await txt2img(text)
        if not job:
            return await update.message.reply_text("API error.")

        await poll_job(update, job)

    elif mode == "stylize":
        if chat not in user_input:
            return await update.message.reply_text("Send image first.")

        await update.message.reply_text("Processing image2image...")

        job = await image2image(user_input[chat], text)
        await poll_job(update, job)

    elif mode == "dop":
        if chat not in user_input:
            return await update.message.reply_text("Send an image first.")

        await update.message.reply_text("Processing video...")

        job = await dop_video(user_input[chat], text)
        await poll_job(update, job)

    elif mode == "status":
        await update.message.reply_text("Checking...")
        status, v, i = await check_status(text)
        await update.message.reply_text(f"Status: {status}\nVideo: {v}\nImage: {i}")

async def poll_job(update, job_id):
    for _ in range(40):
        status, video, image = await check_status(job_id)

        if status == "completed":
            if video:
                await update.message.reply_video(video)
            elif image:
                await update.message.reply_photo(image)
            else:
                await update.message.reply_text("Done but no output.")
            return

        await asyncio.sleep(3)

    await update.message.reply_text("Still processing, try again later.")

def register(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stylize", stylize))
    app.add_handler(CommandHandler("txt2img", txt2img_cmd))
    app.add_handler(CommandHandler("txt2video", txt2video))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT, handle_text))

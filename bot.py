import asyncio
from telegram.ext import (
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    ApplicationBuilder,
    filters,
)
from higgsfield_api import HiggsfieldAPI
from utils import download_file

MODE, = range(1)

user_state = {}


async def start(update, context):
    keyboard = [
        ["🎨 Stylize Image"],
        ["🖼 Text → Image"],
        ["🎬 Text → Video"],
        ["📊 Check Job Status"],
    ]
    await update.message.reply_text("Choose an option:", reply_markup={"keyboard": keyboard, "resize_keyboard": True})
    return MODE


async def mode_selected(update, context):
    choice = update.message.text.lower()

    context.user_data["mode"] = choice
    await update.message.reply_text("Selected: " + choice + "\nNow send input file or prompt.")

    return MODE


async def handle_message(update, context):
    mode = context.user_data.get("mode")

    hf: HiggsfieldAPI = context.bot_data["hf"]

    # 1. TXT → IMG
    if mode.startswith("🖼") or "txt2img" in mode:
        prompt = update.message.text
        await update.message.reply_text("Processing txt2img...")

        job_id, data = await hf.create_job_txt2img(prompt)

        await update.message.reply_text(f"Job ID: {job_id}")
        return MODE

    # 2. TXT → VIDEO
    if mode.startswith("🎬"):
        prompt = update.message.text
        await update.message.reply_text("Processing txt2video...")

        job_id, data = await hf.create_job_txt2video(prompt)
        await update.message.reply_text(f"Job ID: {job_id}")
        return MODE

    # 3. Stylize image (requires photo)
    if mode.startswith("🎨"):
        if not update.message.photo:
            await update.message.reply_text("Send a photo.")
            return MODE

        file = await update.message.photo[-1].get_file()
        local_path = await download_file(file)

        await update.message.reply_text("Stylizing image...")
        job_id, data = await hf.create_job_stylize(local_path)

        await update.message.reply_text(f"Job ID: {job_id}")
        return MODE

    # 4. Job status
    if mode.startswith("📊"):
        job_id = update.message.text

        await update.message.reply_text("Checking status...")
        data = await hf.get_job_status(job_id)

        await update.message.reply_text(str(data))
        return MODE

    return MODE


def register_handlers(app, hf_api):
    app.bot_data["hf"] = hf_api

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MODE: [
                MessageHandler(filters.Regex("^(🎨|🖼|🎬|📊).*"), mode_selected),
                MessageHandler(filters.ALL, handle_message),
            ]
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(conv)

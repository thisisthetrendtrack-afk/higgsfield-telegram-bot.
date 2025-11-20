import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from utils import download_file


# ----------------------------------------------------------
# STATE MACHINE
# ----------------------------------------------------------
STATE = {}   # chat_id → {"mode": "txt2img" | "dop" | …, "image": path}


# ----------------------------------------------------------
# MENU BUTTONS
# ----------------------------------------------------------
def main_menu():
    buttons = [
        [InlineKeyboardButton("🎨 Stylize Image", callback_data="stylize")],
        [InlineKeyboardButton("🖼 Text → Image", callback_data="txt2img")],
        [InlineKeyboardButton("🎬 Text → Video", callback_data="txt2vid")],
        [InlineKeyboardButton("📊 Check Job Status", callback_data="status")],
    ]
    return InlineKeyboardMarkup(buttons)


# ----------------------------------------------------------
# /start
# ----------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to HiggsMasterBot!\nChoose an option:",
        reply_markup=main_menu()
    )


# ----------------------------------------------------------
# Menu Click
# ----------------------------------------------------------
async def menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()

    mode = query.data
    STATE[chat_id] = {"mode": mode}

    await query.message.reply_text(f"Selected: {mode}\nNow send input file or prompt.")


# ----------------------------------------------------------
# Handle Photo
# ----------------------------------------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    mode = STATE.get(chat_id, {}).get("mode")

    telegram_file = await update.message.photo[-1].get_file()
    local_path = await download_file(telegram_file)

    STATE[chat_id]["image"] = local_path

    if mode == "stylize":
        await process_stylize(update, context)
    elif mode == "dop":
        await process_dop(update, context)
    else:
        await update.message.reply_text("Photo saved, now send your prompt.")


# ----------------------------------------------------------
# Handle Text Input (prompt)
# ----------------------------------------------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    mode = STATE.get(chat_id, {}).get("mode")
    user_input = update.message.text
    hf_api = context.bot_data["hf_api"]

    # No mode selected
    if not mode:
        await update.message.reply_text("Choose an option first.", reply_markup=main_menu())
        return

    # txt2img
    if mode == "txt2img":
        await update.message.reply_text("Processing txt2img…")
        job_id, _ = await hf_api.txt2img(user_input)
        await poll_job(update, context, job_id)
        return

    # txt2vid
    if mode == "txt2vid":
        await update.message.reply_text("Processing text → video…")
        job_id, _ = await hf_api.txt2video(user_input)
        await poll_job(update, context, job_id)
        return

    # dop (image required)
    if mode in ["dop", "stylize"]:
        if "image" not in STATE[chat_id]:
            await update.message.reply_text("First send an image.")
            return

        if mode == "dop":
            await process_dop(update, context, user_input)
        if mode == "stylize":
            await process_stylize(update, context, user_input)
        return

    # status check
    if mode == "status":
        await update.message.reply_text("Checking status…")
        status = await hf_api.get_job_status(user_input)
        await update.message.reply_text(str(status))
        return


# ----------------------------------------------------------
# Process: Stylize Image
# ----------------------------------------------------------
async def process_stylize(update, context, prompt=None):
    chat_id = update.message.chat_id
    image = STATE[chat_id]["image"]

    await update.message.reply_text("Processing stylize image…")

    hf_api = context.bot_data["hf_api"]
    job_id, _ = await hf_api.stylize(image, prompt)

    await poll_job(update, context, job_id)


# ----------------------------------------------------------
# Process: DoP Animate
# ----------------------------------------------------------
async def process_dop(update, context, prompt=None):
    chat_id = update.message.chat_id
    image = STATE[chat_id]["image"]
    if not prompt:
        await update.message.reply_text("Send your animation prompt.")
        return

    await update.message.reply_text("Creating DoP video… please wait.")

    hf_api = context.bot_data["hf_api"]
    job_id, _ = await hf_api.create_dop_job(image, prompt)

    await poll_job(update, context, job_id)


# ----------------------------------------------------------
# Job Polling Logic
# ----------------------------------------------------------
async def poll_job(update, context, job_id):
    hf_api = context.bot_data["hf_api"]

    for _ in range(45):
        status = await hf_api.get_job_status(job_id)
        state = status.get("status", "")
        outputs = status.get("outputs", [])

        if state == "completed" and outputs:
            url = outputs[0].get("url")

            # Detect image or video
            if url.endswith(".mp4"):
                await update.message.reply_video(url)
            else:
                await update.message.reply_photo(url)

            return

        await asyncio.sleep(4)

    await update.message.reply_text("Still processing. Try again later.")


# ----------------------------------------------------------
# REGISTER HANDLERS (used by main.py)
# ----------------------------------------------------------
def register_handlers(application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(menu_click))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

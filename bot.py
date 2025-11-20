import os
import asyncio
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from utils import download_file

user_mode = {}  # saves what user selected

# -----------------------
# MAIN MENU
# -----------------------
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎨 Stylize Image", callback_data="stylize")],
        [InlineKeyboardButton("🖼 Text → Image", callback_data="txt2img")],
        [InlineKeyboardButton("🎞 Text → Video", callback_data="txt2video")],
        [InlineKeyboardButton("📊 Check Job Status", callback_data="status")]
    ])

# -----------------------
# /start
# -----------------------
async def start(update, context):
    await update.message.reply_text(
        "Welcome to HiggsMasterBot!",
        reply_markup=main_menu()
    )

# -----------------------
# MENU SELECT
# -----------------------
async def menu_press(update, context):
    query = update.callback_query
    await query.answer()
    user_mode[query.from_user.id] = query.data
    await query.message.reply_text(f"Selected: {query.data}\nNow send input file or prompt.")

# -----------------------
# HANDLE MESSAGES
# -----------------------
async def handle_message(update, context):
    chat_id = update.message.from_user.id
    mode = user_mode.get(chat_id, None)

    if not mode:
        await update.message.reply_text("Choose an option:", reply_markup=main_menu())
        return

    hf = context.bot_data["hf_api"]

    # -----------------------
    # TEXT → IMAGE
    # -----------------------
    if mode == "txt2img":
        prompt = update.message.text
        await update.message.reply_text("Processing txt2img...")

        job, _ = await hf.txt2img(prompt)
        await poll_job_and_return(update, context, job)
        return

    # -----------------------
    # TEXT → VIDEO
    # -----------------------
    if mode == "txt2video":
        prompt = update.message.text
        await update.message.reply_text("Processing text2video...")

        job, _ = await hf.txt2video(prompt)
        await poll_job_and_return(update, context, job)
        return

    # -----------------------
    # STATUS CHECK
    # -----------------------
    if mode == "status":
        job_id = update.message.text.strip()
        status = await hf.get_status(job_id)
        await update.message.reply_text(str(status))
        return

# -----------------------
# HANDLE PHOTO INPUT
# -----------------------
async def handle_photo(update, context):
    chat_id = update.message.from_user.id
    mode = user_mode.get(chat_id, None)

    if not mode:
        await update.message.reply_text("Choose an option:", reply_markup=main_menu())
        return

    hf = context.bot_data["hf_api"]
    file = await update.message.photo[-1].get_file()
    image_path = await download_file(file)
    image_url = await context.bot_data["file_uploader"](image_path)

    if mode == "stylize":
        await update.message.reply_text("Send style prompt (ex: anime, cyberpunk)")
        user_mode[chat_id] = f"stylize|{image_url}"
        return

    if mode.startswith("stylize|"):
        style = update.message.text
        _, img = mode.split("|")

        job, _ = await hf.stylize(img, style)
        await poll_job_and_return(update, context, job)
        return

    # DoP Image → Video
    if mode == "dop":
        text = update.message.caption or "animate"
        job, _ = await hf.dop(image_url, text)
        await poll_job_and_return(update, context, job)
        return

# -----------------------
# POLLING SYSTEM
# -----------------------
async def poll_job_and_return(update, context, job_id):
    hf = context.bot_data["hf_api"]

    for _ in range(45):
        data = await hf.get_status(job_id)
        status = data.get("status")
        outputs = data.get("outputs", [])

        if status == "completed" and outputs:
            url = outputs[0]["url"]

            if url.endswith(".mp4"):
                await update.message.reply_video(url)
            else:
                await update.message.reply_photo(url)
            return

        await asyncio.sleep(4)

    await update.message.reply_text("Job still processing, try again later.")

# -----------------------
# REGISTER HANDLERS
# -----------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_press))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))

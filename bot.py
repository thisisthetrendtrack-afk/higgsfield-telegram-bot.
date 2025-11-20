import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)
from higgsfield_api import HiggsfieldAPI

HF = HiggsfieldAPI(
    hf_key=os.getenv("HF_KEY"),
    hf_secret=os.getenv("HF_SECRET"),
)

USER_STATE = {}


# -----------------------------
#        MAIN MENU
# -----------------------------
def menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 DoP Image → Video", callback_data="dop")],
        [InlineKeyboardButton("🍿 Popcorn I2V", callback_data="popcorn")],
        [InlineKeyboardButton("🧑‍🦰 Face Animate", callback_data="face_animate")],
        [InlineKeyboardButton("👤 Face → Video", callback_data="face2video")],
        [InlineKeyboardButton("⏩ Extend Video", callback_data="extend")],
        [InlineKeyboardButton("🎨 Stylize Image", callback_data="stylize")],
        [InlineKeyboardButton("🖼 Text → Image", callback_data="txt2img")],
        [InlineKeyboardButton("🎞 Text → Video", callback_data="txt2video")],
        [InlineKeyboardButton("📊 Check Job Status", callback_data="status")],
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to Higgsfield Cloud Bot.\nChoose an option:",
        reply_markup=menu_keyboard(),
    )


# -----------------------------
#      CALLBACK BUTTONS
# -----------------------------
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    mode = query.data
    chat = query.message.chat_id

    USER_STATE[chat] = {"mode": mode}

    await query.edit_message_text(f"Selected: {mode}\nNow send input file or prompt.")


# -----------------------------
#      PHOTO / VIDEO INPUT
# -----------------------------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat_id

    if chat not in USER_STATE:
        await update.message.reply_text("Select an option first: /start")
        return

    file = await update.message.photo[-1].get_file()
    local = f"/tmp/{file.file_unique_id}.jpg"
    await file.download_to_drive(local)

    USER_STATE[chat]["file"] = local

    await update.message.reply_text("Photo saved. Now send your prompt.")


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat_id

    file = await update.message.video.get_file()
    local = f"/tmp/{file.file_unique_id}.mp4"
    await file.download_to_drive(local)

    USER_STATE[chat]["file"] = local

    await update.message.reply_text("Video saved. Now send your prompt.")


# -----------------------------
#      TEXT INPUT (PROMPTS)
# -----------------------------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat_id

    if chat not in USER_STATE:
        await update.message.reply_text("Select an option first: /start")
        return

    mode = USER_STATE[chat]["mode"]
    prompt = update.message.text

    await update.message.reply_text(f"Processing {mode}...")

    if mode == "dop":
        job = HF.dop(USER_STATE[chat]["file"], prompt)

    elif mode == "popcorn":
        job = HF.popcorn(USER_STATE[chat]["file"], prompt)

    elif mode == "face_animate":
        job = HF.face_animate(USER_STATE[chat]["file"])

    elif mode == "face2video":
        job = HF.face_to_video(USER_STATE[chat]["file"], prompt)

    elif mode == "extend":
        job = HF.extend_video(USER_STATE[chat]["file"], prompt)

    elif mode == "stylize":
        job = HF.stylize(USER_STATE[chat]["file"], prompt)

    elif mode == "txt2img":
        job = HF.text_to_image(prompt)

    elif mode == "txt2video":
        job = HF.text_to_video(prompt)

    elif mode == "status":
        job = HF.job_status(prompt)
        await update.message.reply_text(str(job))
        return

    else:
        await update.message.reply_text("Unknown mode.")
        return

    job_id = job.get("job_set_id")

    await update.message.reply_text(f"Job started: {job_id}\nChecking status...")

    # Polling
    for _ in range(40):
        status = HF.job_status(job_id)
        state = status.get("state")
        output = status.get("output_url")

        if state == "completed" and output:
            if output.endswith(".mp4"):
                await update.message.reply_video(video=output)
            else:
                await update.message.reply_photo(photo=output)
            return

        await asyncio.sleep(4)

    await update.message.reply_text("Still processing...")


# -----------------------------
#      REGISTER HANDLERS
# -----------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

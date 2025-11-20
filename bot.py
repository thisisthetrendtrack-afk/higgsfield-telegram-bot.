import os
import httpx
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)

HF_KEY = os.getenv("HF_KEY")
HF_SECRET = os.getenv("HF_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

BASE_URL = "https://api.higgsfield.ai/v1"

user_state = {}  # tracks mode per user


# ------------------------------
# START MENU
# ------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎨 Stylize Image", callback_data="stylize")],
        [InlineKeyboardButton("🖼 Text → Image", callback_data="txt2img")],
        [InlineKeyboardButton("🎬 Text → Video", callback_data="txt2video")],
        [InlineKeyboardButton("📊 Check Job Status", callback_data="status")]
    ]
    await update.message.reply_text(
        "Welcome to HiggsMasterBot!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ------------------------------
# BUTTON MENU HANDLERS
# ------------------------------
async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "stylize":
        user_state[user_id] = "stylize"
        await query.edit_message_text("Selected: stylize\nSend an image now.")

    elif query.data == "txt2img":
        user_state[user_id] = "txt2img"
        await query.edit_message_text("Selected: txt2img\nSend your prompt.")

    elif query.data == "txt2video":
        user_state[user_id] = "txt2video"
        await query.edit_message_text("Selected: txt2video\nSend your prompt.")

    elif query.data == "status":
        await query.edit_message_text("Send job_set_id to check status.")
        user_state[user_id] = "status"


# ------------------------------
# MAIN PROMPT HANDLER
# ------------------------------
async def prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    mode = user_state.get(user_id)

    if mode is None:
        await update.message.reply_text("Choose an option first: /start")
        return

    # =============== TXT2IMG ===============
    if mode == "txt2img":
        prompt = update.message.text
        await update.message.reply_text("Starting Text → Image …")

        payload = {
            "model": "flux-1-schnell",
            "prompt": prompt
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/image/generate",
                json=payload,
                headers={"x-api-key": HF_KEY}
            )

        data = r.json()
        if "job_set_id" in data:
            await update.message.reply_text(f"Job submitted.\nJob Set ID: `{data['job_set_id']}`", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"Error: {data}")

    # =============== TXT2VIDEO ===============
    elif mode == "txt2video":
        prompt = update.message.text
        await update.message.reply_text("Starting Text → Video …")

        payload = {
            "model": "dop-turbo",
            "enhance_prompt": True,
            "prompt": prompt
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/image2video/dop",
                json=payload,
                headers={
                    "x-api-key": HF_KEY,
                    "x-api-secret": HF_SECRET
                }
            )

        data = r.json()
        if "job_set_id" in data:
            await update.message.reply_text(f"Job submitted.\nJob Set ID: `{data['job_set_id']}`", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"Error: {data}")

    # =============== STATUS CHECK ===============
    elif mode == "status":
        job_id = update.message.text.strip()
        await update.message.reply_text("Checking job status…")

        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/job-sets/{job_id}",
                headers={"x-api-key": HF_KEY}
            )

        data = r.json()
        await update.message.reply_text(str(data))

    # =============== STYLIZE IMAGE (IMAGE INPUT) ===============
    elif mode == "stylize":
        if not update.message.photo:
            await update.message.reply_text("Send an image.")
            return

        file_id = update.message.photo[-1].file_id
        file = await context.bot.get_file(file_id)
        img_url = file.file_path

        await update.message.reply_text("Stylizing image…")

        payload = {
            "model": "style-diffusion",
            "image_url": img_url
        }

        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{BASE_URL}/image/stylize",
                json=payload,
                headers={"x-api-key": HF_KEY}
            )

        data = r.json()
        if "job_set_id" in data:
            await update.message.reply_text(f"Job submitted.\nJob Set ID: `{data['job_set_id']}`", parse_mode="Markdown")
        else:
            await update.message.reply_text(f"Error: {data}")


# ------------------------------
# CREATE HANDLERS
# ------------------------------
start_handler = CommandHandler("start", start)
button_handler = CallbackQueryHandler(button_router)
message_handler = MessageHandler(filters.TEXT | filters.PHOTO, prompt_handler)

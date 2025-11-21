import os
import asyncio
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ApplicationBuilder,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from higgsfield_api import HiggsfieldAPI

# ---------------------------
# ADMIN + LIMITS
# ---------------------------
ADMIN_ID = 7872634386     # Your Telegram ID
GEN_LIMIT = 2             # Normal users: 2 generations max
user_usage = {}           # Track user usage

# SESSION MEMORY
user_sessions = {}

# ---------------------------
# START COMMAND
# ---------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")]
    ]

    welcome_text = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "Create HD images using official Higgsfield Cloud.\n\n"
        "✨ Bot by @honeyhoney44\n"
        "➡️ For Special Prompts Join Channel: @HiggsMasterBot\n"
        "⚡ Admin unlimited | Users get *2 free generations*\n\n"
        "Select an option below:"
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ---------------------------
# BUTTON HANDLER
# ---------------------------
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()

    mode = query.data
    chat_id = query.message.chat_id

    user_sessions[chat_id] = {"mode": mode}

    await query.edit_message_text(
        "📝 Send your *text prompt* to generate image.",
        parse_mode="Markdown"
    )

# ----------------------------------------------------
# LOADING ANIMATION
# ----------------------------------------------------
async def loading_animation(context, chat_id, message_id, stop_event):
    frames = [
        "⏳ Step 1: Sending request…",
        "🔄 Step 2: Model processing…",
        "✨ Step 3: Finalizing…"
    ]
    i = 0

    while not stop_event.is_set():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=frames[i % len(frames)]
            )
        except:
            pass
        i += 1
        await asyncio.sleep(3)

# ---------------------------
# TEXT HANDLER
# ---------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text
    user_id = chat_id

    # Check if they selected a menu option
    if chat_id not in user_sessions:
        await update.message.reply_text("Please select an option using /start")
        return

    # ---------------------------
    # GENERATION LIMIT CHECK
    # ---------------------------
    if user_id != ADMIN_ID:
        user_usage[user_id] = user_usage.get(user_id, 0)

        if user_usage[user_id] >= GEN_LIMIT:
            await update.message.reply_text(
                "⚠️ You have used your *2 free generations*.\n"
                "✨ Join @HiggsMasterBot for more prompts!"
            )
            return

    mode = user_sessions[chat_id]["mode"]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    MODEL = "higgsfield-ai/soul/standard"

    loading_msg = await update.message.reply_text("⏳ Loading…")
    stop_event = asyncio.Event()

    context.application.create_task(
        loading_animation(context, chat_id, loading_msg.message_id, stop_event)
    )

    # ------------------------------
    # TEXT → IMAGE
    # ------------------------------
    if mode == "text2image":
        payload = {"prompt": text}

        resp = hf.submit(MODEL, payload)
        req_id = resp["request_id"]

        final = hf.wait_for_result(req_id)
        stop_event.set()

        if final.get("status") == "completed":
            image_url = final["images"][0]["url"]

            await update.message.reply_photo(image_url)

            if user_id != ADMIN_ID:
                user_usage[user_id] += 1

        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")

# ---------------------------
# REGISTER HANDLERS
# ---------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

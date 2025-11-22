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
import requests

# -----------------------------
# GLOBAL MEMORY
# -----------------------------
user_sessions = {}
user_limits = {}   # Track usage
ADMIN_ID = 7872634386
MAX_FREE = 2        # Free users get 2 generations

# -----------------------------
# START
# -----------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")]
    ]

    msg = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "✨ Bot by @honeyhoney44\n\n"
        "📌 You get *2 free generations*\n"
        "🔔 For prompts & tutorials subscribe: @HiggsMasterBotChannel\n\n"
        "Select an option below:"
    )

    await update.message.reply_text(
        msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )

# -----------------------------
# BUTTON HANDLER
# -----------------------------
async def button_handler(update, context):
    q = update.callback_query
    await q.answer()

    mode = q.data
    chat_id = q.message.chat_id

    user_sessions[chat_id] = {"mode": mode}

    if mode == "text2image":
        await q.edit_message_text(
            "📝 Send your *text prompt* below:", parse_mode="Markdown"
        )

# -----------------------------
# PROGRESS BAR (B1)
# -----------------------------
async def progress_bar(context, chat_id, message_id, stop_event):
    bars = [
        "[▓░░░░░░░░] 10%",
        "[▓▓▓░░░░░░] 30%",
        "[▓▓▓▓▓░░░░] 50%",
        "[▓▓▓▓▓▓▓░░] 70%",
        "[▓▓▓▓▓▓▓▓▓] 90%",
        "[▓▓▓▓▓▓▓▓▓▓] 100%"
    ]

    i = 0
    while not stop_event.is_set():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"⏳ Generating...\n{bars[i % len(bars)]}"
            )
        except:
            pass
        i += 1
        await asyncio.sleep(2)

# -----------------------------
# TEXT HANDLER (IMAGE GEN)
# -----------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    # No mode selected
    if chat_id not in user_sessions:
        await update.message.reply_text("Please choose from the menu using /start")
        return

    mode = user_sessions[chat_id]["mode"]

    # Limit: Admin unlimited
    if chat_id != ADMIN_ID:
        count = user_limits.get(chat_id, 0)
        if count >= MAX_FREE:
            await update.message.reply_text(
                "⚠ You reached your *2 free generations*.\n"
                "Subscribe for unlimited access:\n@HiggsMasterBotChannel"
            )
            return

    # Log prompts to admin
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📝 User `{chat_id}` prompt:\n{text}",
            parse_mode="Markdown"
        )
    except:
        pass

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    MODEL = "higgsfield-ai/soul/standard"

    # Start progress bar
    loading_msg = await update.message.reply_text("⏳ Generating…")
    stop_evt = asyncio.Event()

    context.application.create_task(
        progress_bar(context, chat_id, loading_msg.message_id, stop_evt)
    )

    # IMAGE GENERATION
    if mode == "text2image":
        payload = {"prompt": text}

        resp = hf.submit(MODEL, payload)
        req_id = resp["request_id"]

        final = hf.wait_for_result(req_id)
        stop_evt.set()

        if final.get("status") == "completed":
            # Count usage
            if chat_id != ADMIN_ID:
                user_limits[chat_id] = user_limits.get(chat_id, 0) + 1

            await update.message.reply_photo(final["images"][0]["url"])
            await update.message.reply_text(
                "🎉 Your image is ready! Enjoy.\n"
                "Don’t forget to subscribe: @HiggsMasterBotChannel"
            )
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")

# -----------------------------
# REGISTER
# -----------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

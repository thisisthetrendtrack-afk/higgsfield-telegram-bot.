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

# -----------------------------
# CONFIG
# -----------------------------
ADMIN_ID = 7872634386          # Admin unlimited
user_usage = {}                # Tracks generation count per user

# -----------------------------
# START COMMAND
# -----------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
    ]

    welcome_text = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "Create HD images using official Higgsfield Cloud.\n\n"
        "✨ Bot by @honeyhoney44\n"
        "➡️ For Special Prompts Join Channel: @HiggsMasterBot\n\n"
        "Select an option below:"
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# -----------------------------
# BUTTON HANDLER
# -----------------------------
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id

    user_usage.setdefault(chat_id, 0)
    context.user_data["mode"] = query.data

    if query.data == "text2image":
        await query.edit_message_text(
            "📝 Send your *text prompt* for Image Generation.",
            parse_mode="Markdown"
        )

# -----------------------------
# LOADING ANIMATION
# -----------------------------
async def loading_animation(context, chat_id, message_id, stop_event):
    frames = [
        "⏳ Step 1: Sending request...",
        "🔄 Step 2: Processing...",
        "🎨 Step 3: Rendering image...",
        "✨ Step 4: Finalizing..."
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
        await asyncio.sleep(4)

# -----------------------------
# TEXT HANDLER
# -----------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    prompt = update.message.text
    mode = context.user_data.get("mode")

    if not mode:
        await update.message.reply_text("Please choose from menu using /start")
        return

    # USER LIMITATION (except admin)
    if chat_id != ADMIN_ID:
        user_usage.setdefault(chat_id, 0)
        if user_usage[chat_id] >= 2:
            await update.message.reply_text(
                "❌ You reached your free limit.\nJoin @HiggsMasterBot for prompts."
            )
            return

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    MODEL = "higgsfield-ai/soul/standard"

    loading_msg = await update.message.reply_text("⏳ Loading…")
    stop_event = asyncio.Event()
    context.application.create_task(
        loading_animation(context, chat_id, loading_msg.message_id, stop_event)
    )

    if mode == "text2image":
        payload = {"prompt": prompt}

        resp = hf.submit(MODEL, payload)
        req_id = resp["request_id"]
        final = hf.wait_for_result(req_id)

        stop_event.set()

        if final.get("status") == "completed":
            url = final["images"][0]["url"]
            await update.message.reply_photo(url)
            if chat_id != ADMIN_ID:
                user_usage[chat_id] += 1
        else:
            await update.message.reply_text(
                f"❌ Failed: {final.get('status')}"
            )

# -----------------------------
# REGISTER HANDLERS
# -----------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

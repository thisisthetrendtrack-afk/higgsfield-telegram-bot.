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

# GLOBAL SESSION MEMORY
user_sessions = {}


# ---------------------------
# START COMMAND
# ---------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
    ]

    welcome_text = (
        "🤖 *Welcome to HiggsMasterBot*\n"
        "Create stunning AI images using official Higgsfield Cloud.\n\n"
        "👤 Bot by @honeyhoney44\n"
        "📢 *Please subscribe to our channel:* @HiggsMasterBot\n"
        "You will receive high-quality prompts, updates and new features there.\n\n"
        "✨ *Example prompts:*\n"
        "• Cat riding a bicycle on the road\n"
        "• Beautiful sunset over the ocean\n"
        "• Hyper-realistic portrait of an old man\n"
        "• Cute puppy reading a book in a library\n\n"
        "Tap below to start:"
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

    if mode == "text2image":
        await query.edit_message_text(
            "📝 Send your *text prompt* for Image Generation.", parse_mode="Markdown"
        )


# ----------------------------------------------------
#  STEP-BY-STEP LOADING
# ----------------------------------------------------
async def loading_animation(context, chat_id, message_id, stop_event):
    frames = [
        "⏳ Step 1: Sending request…",
        "🔄 Step 2: Model processing…",
        "🎨 Step 3: Rendering image…",
        "✨ Step 4: Finalizing output…"
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


# ---------------------------
# TEXT HANDLER
# ---------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    if chat_id not in user_sessions:
        await update.message.reply_text("Please choose from the menu using /start")
        return

    mode = user_sessions[chat_id]["mode"]

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    IMAGE_MODEL = "higgsfield-ai/soul/standard"

    # Start loading animation
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

        resp = hf.submit(IMAGE_MODEL, payload)
        req_id = resp["request_id"]
        final = hf.wait_for_result(req_id)

        stop_event.set()

        if final.get("status") == "completed":
            await update.message.reply_photo(final["images"][0]["url"])
            await update.message.reply_text("✅ Image generated successfully.")
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")


# ---------------------------
# REGISTER HANDLERS
# ---------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

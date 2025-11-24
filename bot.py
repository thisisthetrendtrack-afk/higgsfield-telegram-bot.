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
from nano_banana_api import NanoBananaAPI
import requests

# ---------------------------
# CONFIG
# ---------------------------
ADMIN_ID = 7872634386
GEN_LIMIT = 2

# USER DATA (sessions + usage counter)
user_sessions = {}
user_usage = {}     # {chat_id: count}

# ---------------------------
# START COMMAND
# ---------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🍌 Nano Pro (Text → Image)", callback_data="nano_text")]
    ]

    welcome = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "Fast, clean and high quality image generation.\n\n"
        "✨ Bot by @honeyhoney44\n"
        "🔔 For advanced prompts: *Join @HiggsMasterBotChannel*\n\n"
        "Select an option below."
    )

    await update.message.reply_text(
        welcome,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ---------------------------
# BUTTON HANDLER
# ---------------------------
async def button_handler(update, context):
    query = update.callback_query
    chat_id = query.message.chat_id
    await query.answer()

    if query.data == "text2image":
        user_sessions[chat_id] = {"mode": "text2image"}
        await query.edit_message_text(
            "📝 Send your *image prompt*.\n"
            "Example: `Ultra realistic cat driving car, 4k, cinema lighting`",
            parse_mode="Markdown"
        )

    elif query.data == "nano_text":
        user_sessions[chat_id] = {"mode": "nano_text"}
        await query.edit_message_text(
            "🍌 Send your *Nano Pro prompt*.\n"
            "Example: `Banana warrior riding neon dragon, 4k`",
            parse_mode="Markdown"
        )

# ----------------------------------------------------
# PROFESSIONAL LOADING ANIMATION
# ----------------------------------------------------
async def loading_animation(context, chat_id, message_id, stop_event):
    frames = [
        "⏳ Preparing your request…",
        "🔄 Model running…",
        "🎨 AI painting your image…",
        "✨ Finalizing artwork…"
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

# ----------------------------------------------------
# TEXT HANDLER
# ----------------------------------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text

    # No session selected
    if chat_id not in user_sessions:
        await update.message.reply_text("Use /start first.")
        return

    mode = user_sessions[chat_id]["mode"]

    # ---------------------------
    # DAILY LIMIT CHECK
    # ---------------------------
    if chat_id != ADMIN_ID:
        count = user_usage.get(chat_id, 0)
        if count >= GEN_LIMIT:
            await update.message.reply_text(
                "❌ *Daily Limit Reached*\n"
                "You have used all 2 free generations.\n"
                "Subscribe @HiggsMasterBotChannel to unlock more.",
                parse_mode="Markdown"
            )
            return

    # Log prompt to admin
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📝 *User:* `{chat_id}`\n*Prompt:* {text}",
            parse_mode="Markdown"
        )
    except:
        pass

    # Start loading animation
    loading_msg = await update.message.reply_text("⏳ Loading…")
    stop_event = asyncio.Event()
    context.application.create_task(
        loading_animation(context, chat_id, loading_msg.message_id, stop_event)
    )

    # ==========================================================
    # NANO PRO TEXT → IMAGE
    # ==========================================================
    if mode == "nano_text":
        api = NanoBananaAPI()

        try:
            task = api.create_task(prompt=text)
            task_id = task["data"]["taskId"]
        except Exception as e:
            stop_event.set()
            await update.message.reply_text(f"❌ Nano Pro Error: {str(e)}")
            return

        import json
        # Poll until complete
        while True:
            info = api.check_task(task_id)
            state = info["data"]["state"]

            if state == "success":
                break
            elif state == "fail":
                stop_event.set()
                await update.message.reply_text("❌ Nano Pro generation failed.")
                return

            await asyncio.sleep(2)

        stop_event.set()

        # Extract final image
        result_json = json.loads(info["data"]["resultJson"])
        url = result_json["resultUrls"][0]

        await update.message.reply_photo(url)

        # Increase user usage
        if chat_id != ADMIN_ID:
            user_usage[chat_id] = user_usage.get(chat_id, 0) + 1

        return

    # ==========================================================
    # HIGGSFIELD TEXT → IMAGE
    # ==========================================================
    if mode == "text2image":
        hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
        MODEL = "higgsfield-ai/soul/standard"

        payload = {"prompt": text}

        try:
            resp = hf.submit(MODEL, payload)
            req_id = resp["request_id"]
            final = hf.wait_for_result(req_id)
        except Exception as e:
            stop_event.set()
            await update.message.reply_text(f"❌ Error: {str(e)}")
            return

        stop_event.set()

        if final.get("status") == "completed":
            await update.message.reply_photo(final["images"][0]["url"])

            # increase user usage
            if chat_id != ADMIN_ID:
                user_usage[chat_id] = user_usage.get(chat_id, 0) + 1

        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")

# ---------------------------
# REGISTER HANDLERS
# ---------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

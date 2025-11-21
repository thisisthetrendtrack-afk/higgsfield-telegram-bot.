import os
import asyncio
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from higgsfield_api import HiggsfieldAPI

# CHANNEL REQUIREMENT
CHANNEL_USERNAME = "@HiggsMasterBot"

user_sessions = {}


# ----------------------------------------------------
# CHECK SUBSCRIPTION
# ----------------------------------------------------
async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False


# ----------------------------------------------------
# START COMMAND
# ----------------------------------------------------
async def start(update, context):
    user_id = update.message.from_user.id

    subscribed = await is_subscribed(context.bot, user_id)

    if not subscribed:
        keyboard = [
            [
                InlineKeyboardButton("🔔 Subscribe Now", url=f"https://t.me/{CHANNEL_USERNAME.replace('@','')}"),
                InlineKeyboardButton("✔ I Subscribed", callback_data="check_sub"),
            ]
        ]

        await update.message.reply_text(
            "⚠ To use this bot, you must subscribe to our channel:\n"
            f"{CHANNEL_USERNAME}\n\n"
            "After subscribing, press **I Subscribed**.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # If subscribed → show menu
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")]
    ]

    await update.message.reply_text(
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "Create high-quality images using Higgsfield Cloud.\n\n"
        "✨ Bot by @honeyhoney44",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ----------------------------------------------------
# CHECK SUB BUTTON
# ----------------------------------------------------
async def button_handler(update, context):
    query = update.callback_query
    user_id = query.from_user.id

    if query.data == "check_sub":
        subscribed = await is_subscribed(context.bot, user_id)

        if subscribed:
            await query.edit_message_text("✅ Subscription verified!\nSend /start again.")
        else:
            await query.answer("❌ You are not subscribed.", show_alert=True)
        return

    # MENU HANDLING
    mode = query.data
    chat_id = query.message.chat_id

    user_sessions[chat_id] = {"mode": mode}

    if mode == "text2image":
        await query.edit_message_text("📝 Send your *text prompt* to generate an image.", parse_mode="Markdown")


# ----------------------------------------------------
# LOADING ANIMATION
# ----------------------------------------------------
async def loading_animation(context, chat_id, message_id, stop_event):
    frames = [
        "⏳ Step 1: Sending request…",
        "🔄 Step 2: Model processing…",
        "🎨 Step 3: Generating image…",
        "✨ Step 4: Finalizing…"
    ]
    i = 0
    while not stop_event.is_set():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=frames[i % len(frames)]
            )
        except:
            pass
        i += 1
        await asyncio.sleep(3)


# ----------------------------------------------------
# MESSAGE HANDLER
# ----------------------------------------------------
async def message_handler(update, context):
    chat_id = update.message.chat_id
    prompt = update.message.text

    if chat_id not in user_sessions:
        await update.message.reply_text("Please use /start")
        return

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    MODEL = "higgsfield-ai/soul/standard"

    loading_msg = await update.message.reply_text("⏳ Loading…")
    stop_event = asyncio.Event()

    context.application.create_task(
        loading_animation(context, chat_id, loading_msg.message_id, stop_event)
    )

    resp = hf.submit(MODEL, {"prompt": prompt})
    req_id = resp["request_id"]

    final = hf.wait_for_result(req_id)
    stop_event.set()

    if final.get("status") == "completed":
        await update.message.reply_photo(final["images"][0]["url"])
        await update.message.reply_text("✅ Image generated successfully.")
    else:
        await update.message.reply_text(f"❌ Failed: {final.get('status')}")


# ----------------------------------------------------
# REGISTER HANDLERS
# ----------------------------------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

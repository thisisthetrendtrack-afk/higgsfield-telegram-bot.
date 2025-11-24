import os
import json
import asyncio
import logging
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
# CONFIGURATION
# -----------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

ADMIN_ID = 7872634386
MAX_FREE = 2
DATA_FILE = "/app/storage/data.json"  # Must match Railway Volume path

user_sessions = {}  # Temporary session memory

# -----------------------------
# DATABASE FUNCTIONS
# -----------------------------
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f).get("users", {})
        except Exception as e:
            print(f"⚠️ Could not load data: {e}")
            return {}
    return {}

def save_data(user_limits):
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w") as f:
            json.dump({"users": user_limits}, f)
    except Exception as e:
        print(f"⚠️ Could not save data: {e}")

# Load limits on startup
user_limits = load_data()

# -----------------------------
# /START COMMAND
# -----------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🎥 Image → Video", callback_data="image2video")]
    ]
    
    msg = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "✨ Create cinematic videos & images.\n\n"
        "📌 You get *2 free generations*\n"
        "Choose your mode:"
    )
    
    await update.message.reply_text(
        msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard)
    )

# -----------------------------
# MENU BUTTON HANDLER
# -----------------------------
async def button_handler(update, context):
    q = update.callback_query
    await q.answer()
    
    mode = q.data
    chat_id = q.message.chat_id
    
    # Initialize session
    user_sessions[chat_id] = {"mode": mode, "step": "waiting_input"}

    if mode == "text2image":
        await q.edit_message_text("📝 *Text to Image Mode*\nSend your prompt below:")
    elif mode == "image2video":
        await q.edit_message_text("🎥 *Image to Video Mode*\nFirst, send me the **Photo** you want to animate.")

# -----------------------------
# PHOTO HANDLER (For Video)
# -----------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id)

    # 1. Validation
    if not session or session.get("mode") != "image2video":
        await update.message.reply_text("⚠ Please select '🎥 Image → Video' from /start first.")
        return

    status_msg = await update.message.reply_text("📥 Processing image...")

    try:
        # 2. Get File Link
        photo_obj = await update.message.photo[-1].get_file()
        
        # This gets the public URL from Telegram servers
        image_url = photo_obj.link 

        # 3. Store in Session
        session["image_url"] = image_url
        session["step"] = "waiting_prompt"

        print(f"📸 Image captured for {chat_id}: {image_url}")
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text="✅ **Image received!**\n\nNow send a **text prompt** to animate it (e.g., 'Zoom in', 'The character smiles').",
            parse_mode="Markdown"
        )

    except Exception as e:
        print(f"❌ Photo Error: {e}")
        await update.message.reply_text("❌ Failed to process image. Please try again.")

# -----------------------------
# TEXT HANDLER (Generation)
# -----------------------------
async def text_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text
    session = user_sessions.get(chat_id)

    if not session:
        await update.message.reply_text("Please start with /start")
        return

    # 1. Check Limits
    if chat_id != ADMIN_ID:
        count = user_limits.get(str(chat_id), 0)
        if count >= MAX_FREE:
            await update.message.reply_text("❌ You have used your 2 free generations.")
            return

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    
    # 2. Prepare Payload
    payload = {}
    model_id = ""

    if session["mode"] == "text2image":
        model_id = "higgsfield-ai/soul/standard"
        payload = {"prompt": text}
        await update.message.reply_text(f"🎨 Generating Image...")

    elif session["mode"] == "image2video":
        if session.get("step") != "waiting_prompt":
            await update.message.reply_text("Please send an image first!")
            return
            
        # Using the PREVIEW model as requested
        model_id = "higgsfield-ai/dop/preview"
        
        payload = {
            "prompt": text,
            "image_url": session["image_url"]
        }
        await update.message.reply_text(f"🎬 Generating Video...\n(This usually takes 30-60 seconds)")

    # 3. Execute API Call
    try:
        # Submit
        resp = hf.submit(model_id, payload)
        req_id = resp["request_id"]

        # Wait for result (Async)
        final = await hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            # Update Limits
            if chat_id != ADMIN_ID:
                user_limits[str(chat_id)] = user_limits.get(str(chat_id), 0) + 1
                save_data(user_limits)

            # Send Result
            media_url = final["images"][0]["url"]
            
            if session["mode"] == "image2video":
                await update.message.reply_video(media_url, caption="✨ Here is your video!")
            else:
                await update.message.reply_photo(media_url, caption="✨ Here is your image!")
        else:
            await update.message.reply_text(f"❌ Generation Failed: {final.get('status')}")

    except Exception as e:
        print(f"❌ Logic Error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

# -----------------------------
# MAIN APP BUILDER
# -----------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))


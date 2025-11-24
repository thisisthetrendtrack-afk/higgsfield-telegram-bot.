import os
import json
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
ADMIN_ID = 7872634386  # Your Admin ID
MAX_FREE = 2
DATA_FILE = "/app/storage/data.json" # Persistent path for Railway

# Memory for active sessions (temporary)
user_sessions = {}

# -----------------------------
# PERSISTENCE (SAVE/LOAD)
# -----------------------------
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f).get("users", {})
        except:
            return {}
    return {}

def save_data(user_limits):
    # Ensure directory exists
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump({"users": user_limits}, f)

# Load once on start
user_limits = load_data()

# -----------------------------
# START COMMAND
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
# MENU HANDLER
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

    if not session or session["mode"] != "image2video":
        await update.message.reply_text("⚠ Please select 'Image → Video' from /start first.")
        return

    # Get highest quality photo
    photo_file = await update.message.photo[-1].get_file()
    image_url = photo_file.file_path

    session["image_url"] = image_url
    session["step"] = "waiting_prompt"
    
    await update.message.reply_text(
        "✅ Image received!\n\nNow send a **text prompt** describing the motion (e.g., 'Zoom in', 'Pan right')."
    )

# -----------------------------
# TEXT HANDLER (Prompts)
# -----------------------------
async def text_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text
    session = user_sessions.get(chat_id)

    if not session:
        await update.message.reply_text("Please start with /start")
        return

    # Check Limits
    if chat_id != ADMIN_ID:
        count = user_limits.get(str(chat_id), 0)
        if count >= MAX_FREE:
            await update.message.reply_text("❌ You have used your 2 free generations.")
            return

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    
    # Setup Request
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
            
        model_id = "higgsfield-ai/dop"  # Video Model
        payload = {
            "prompt": text,
            "image_url": session["image_url"]
        }
        await update.message.reply_text(f"🎬 Generating Video... (This takes time)")

    # Execute
    try:
        resp = hf.submit(model_id, payload)
        req_id = resp["request_id"]

        final = await hf.wait_for_result(req_id)

        if final.get("status") == "completed":
            # Update Limits
            if chat_id != ADMIN_ID:
                user_limits[str(chat_id)] = user_limits.get(str(chat_id), 0) + 1
                save_data(user_limits)

            media_url = final["images"][0]["url"]
            
            if session["mode"] == "image2video":
                await update.message.reply_video(media_url, caption="✨ Here is your video!")
            else:
                await update.message.reply_photo(media_url, caption="✨ Here is your image!")
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# -----------------------------
# REGISTER
# -----------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

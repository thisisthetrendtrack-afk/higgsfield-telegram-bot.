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
# 1. CONFIGURATION
# -----------------------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

ADMIN_ID = 7872634386
MAX_FREE = 2
DATA_FILE = "/app/storage/data.json"  # Railway Persistent Volume

user_sessions = {}

# -----------------------------
# 2. PERSISTENCE
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

user_limits = load_data()

# -----------------------------
# 3. START COMMAND
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
# 4. MENU HANDLER
# -----------------------------
async def button_handler(update, context):
    q = update.callback_query
    await q.answer()
    
    mode = q.data
    chat_id = q.message.chat_id
    
    user_sessions[chat_id] = {"mode": mode, "step": "waiting_input"}

    if mode == "text2image":
        await q.edit_message_text("📝 *Text to Image Mode*\nSend your prompt below:")
    elif mode == "image2video":
        await q.edit_message_text("🎥 *Image to Video Mode*\nFirst, send me the **Photo** you want to animate.")

# -----------------------------
# 5. PHOTO HANDLER
# -----------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id)

    if not session or session.get("mode") != "image2video":
        await update.message.reply_text("⚠ Please select '🎥 Image → Video' from /start first.")
        return

    status_msg = await update.message.reply_text("📥 Processing image...")

    try:
        photo_obj = await update.message.photo[-1].get_file()
        
        # Manually construct URL to ensure it works
        file_path = photo_obj.file_path
        if file_path.startswith("http"):
            image_url = file_path
        else:
            image_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file_path}"
            
        session["image_url"] = image_url
        session["step"] = "waiting_prompt"

        print(f"📸 Image linked: {image_url}")
        
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text="✅ **Image received!**\n\nNow send a **text prompt** to animate it (e.g., 'Zoom in', 'The character smiles').",
            parse_mode="Markdown"
        )

    except Exception as e:
        print(f"❌ Photo Error: {e}")
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"❌ **Error:**\n`{str(e)}`",
            parse_mode="Markdown"
        )

# -----------------------------
# 6. TEXT HANDLER (GENERATION)
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
            
        # --- FIXED MODEL NAME HERE ---
        # Changed 'preview' to 'turbo' based on the error message
        model_id = "higgsfield-ai/dop/turbo"
        
        payload = {
            "prompt": text,
            "image_url": session["image_url"]
        }
        await update.message.reply_text(f"🎬 Generating Video (Turbo Mode)...\n(This takes ~30-60s)")

    try:
        resp = hf.submit(model_id, payload)
        req_id = resp["request_id"]

        final = await hf.wait_for_result(req_id)

        if final.get("status") == "completed":
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
        print(f"❌ API Error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

# -----------------------------
# 7. REGISTER
# -----------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

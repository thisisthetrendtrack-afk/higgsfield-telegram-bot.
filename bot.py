import os
import json
import asyncio
import logging
from datetime import datetime
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
MAX_FREE_DAILY = 2  # 2 Generations per day
DATA_FILE = "/app/storage/data.json"

# -----------------------------
# 2. PERSISTENCE (SAVE/LOAD)
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

# Load data on start
user_limits = load_data()
user_sessions = {}

# -----------------------------
# 3. HELPER: DAILY LIMIT CHECKER
# -----------------------------
def check_limit(chat_id):
    """
    Returns True if user can generate, False if limit reached.
    Resets count if it's a new day.
    """
    # 1. Admin is always allowed
    if chat_id == ADMIN_ID:
        return True

    cid = str(chat_id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Get user data or initialize
    user_data = user_limits.get(cid, {"count": 0, "date": today})

    # 2. Check if it's a new day -> Reset
    if user_data.get("date") != today:
        user_data = {"count": 0, "date": today}
        user_limits[cid] = user_data # Update memory
        save_data(user_limits)       # Save reset

    # 3. Check Count
    if user_data["count"] >= MAX_FREE_DAILY:
        return False
    
    return True

def increment_usage(chat_id):
    """Increments the usage counter for the user."""
    if chat_id == ADMIN_ID:
        return

    cid = str(chat_id)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Update count
    current = user_limits.get(cid, {"count": 0, "date": today})
    current["count"] += 1
    current["date"] = today # Ensure date is current
    
    user_limits[cid] = current
    save_data(user_limits)

# -----------------------------
# 4. PROGRESS BAR ANIMATION
# -----------------------------
async def animate_progress(context, chat_id, message_id, stop_event):
    bars = [
        "⏳ Starting...\n[░░░░░░░░░░] 0%",
        "🎨 Sketching...\n[▓▓░░░░░░░░] 20%",
        "🎨 Coloring...\n[▓▓▓▓░░░░░░] 40%",
        "🎬 Rendering...\n[▓▓▓▓▓▓░░░░] 60%",
        "✨ Polishing...\n[▓▓▓▓▓▓▓▓░░] 80%",
        "🚀 Finalizing...\n[▓▓▓▓▓▓▓▓▓▓] 99%"
    ]
    i = 0
    while not stop_event.is_set():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"{bars[i % len(bars)]}\n\n_Please wait..._",
                parse_mode="Markdown"
            )
        except: pass
        i += 1
        await asyncio.sleep(6)

# -----------------------------
# 5. START & MENU
# -----------------------------
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🎥 Image → Video", callback_data="image2video")]
    ]
    msg = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "✨ Create cinematic videos & images.\n\n"
        f"📌 Limit: *{MAX_FREE_DAILY} generations per day*\n"
        "Choose your mode:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update, context):
    q = update.callback_query
    await q.answer()
    mode = q.data
    chat_id = q.message.chat_id
    user_sessions[chat_id] = {"mode": mode, "step": "waiting_input"}

    if mode == "text2image":
        await q.edit_message_text("📝 *Text to Image*\nSend your prompt:")
    elif mode == "image2video":
        await q.edit_message_text("🎥 *Image to Video*\nFirst, send the **Photo**.")

# -----------------------------
# 6. PHOTO HANDLER
# -----------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id)

    if not session or session.get("mode") != "image2video":
        await update.message.reply_text("⚠ Select '🎥 Image → Video' from /start first.")
        return

    status_msg = await update.message.reply_text("📥 Processing image...")

    try:
        photo_obj = await update.message.photo[-1].get_file()
        file_path = photo_obj.file_path
        image_url = file_path if file_path.startswith("http") else f"https://api.telegram.org/file/bot{context.bot.token}/{file_path}"
            
        session["image_url"] = image_url
        session["step"] = "waiting_prompt"

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text="✅ **Image Linked!**\nNow send a **text prompt**.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"❌ Error: {e}")

# -----------------------------
# 7. GENERATION HANDLER
# -----------------------------
async def text_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text
    session = user_sessions.get(chat_id)

    if not session:
        await update.message.reply_text("Please start with /start")
        return

    # --- CHECK DAILY LIMIT ---
    if not check_limit(chat_id):
        await update.message.reply_text("❌ **Daily Limit Reached**\nYou have used your 2 free generations for today.\nTry again tomorrow!")
        return

    # --- ADMIN LOG ---
    try:
        user_name = update.message.from_user.first_name
        await context.bot.send_message(
            chat_id=ADMIN_ID, 
            text=f"🕵️ **Log**\n👤 {user_name} (`{chat_id}`)\n🎯 {session['mode']}\n📝 {text}",
            parse_mode="Markdown"
        )
    except: pass

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    
    # Setup
    payload = {}
    model_id = ""
    status_msg = await update.message.reply_text("⏳ Initializing...")

    if session["mode"] == "text2image":
        model_id = "higgsfield-ai/soul/standard"
        payload = {"prompt": text}
    elif session["mode"] == "image2video":
        if session.get("step") != "waiting_prompt":
            await update.message.reply_text("Send an image first!")
            return
        model_id = "higgsfield-ai/dop/turbo"
        payload = {"prompt": text, "image_url": session["image_url"]}

    # Animation
    stop_event = asyncio.Event()
    asyncio.create_task(animate_progress(context, chat_id, status_msg.message_id, stop_event))

    try:
        resp = hf.submit(model_id, payload)
        final = await hf.wait_for_result(resp["request_id"])
        
        stop_event.set() # Stop animation

        if final.get("status") == "completed":
            # --- INCREMENT USAGE ---
            increment_usage(chat_id)

            # Smart URL Finder
            media_url = None
            if "images" in final: media_url = final["images"][0]["url"]
            elif "video" in final:
                v = final["video"]
                media_url = v.get("url") if isinstance(v, dict) else (v[0].get("url") if isinstance(v, list) else v)
            elif "output_url" in final: media_url = final["output_url"]
            elif "result" in final: media_url = final["result"]

            if not media_url: raise ValueError(f"No URL found: {final.keys()}")

            if session["mode"] == "image2video":
                await update.message.reply_video(media_url, caption="✨ Here is your video!")
            else:
                await update.message.reply_photo(media_url, caption="✨ Here is your image!")
            
            await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")

    except Exception as e:
        stop_event.set()
        await update.message.reply_text(f"❌ Error: {e}")

# -----------------------------
# 8. REGISTER
# -----------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

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
MAX_FREE_DAILY = 2
DATA_FILE = "/app/storage/data.json"

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
user_sessions = {}

# -----------------------------
# 3. HELPER: LIMIT CHECKER
# -----------------------------
def check_limit(chat_id):
    if chat_id == ADMIN_ID: return True

    cid = str(chat_id)
    today = datetime.now().strftime("%Y-%m-%d")
    user_data = user_limits.get(cid, {"count": 0, "date": today})

    if user_data.get("date") != today:
        user_data = {"count": 0, "date": today}
        user_limits[cid] = user_data
        save_data(user_limits)

    if user_data["count"] >= MAX_FREE_DAILY:
        return False
    return True

def increment_usage(chat_id):
    if chat_id == ADMIN_ID: return
    cid = str(chat_id)
    today = datetime.now().strftime("%Y-%m-%d")
    current = user_limits.get(cid, {"count": 0, "date": today})
    current["count"] += 1
    current["date"] = today
    user_limits[cid] = current
    save_data(user_limits)

# -----------------------------
# 4. ANIMATION
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
# 5. COMMANDS & MENU
# -----------------------------
async def start(update, context):
    # Updated Keyboard with 3 Options
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🎥 Higgsfield Video", callback_data="image2video")],
        [InlineKeyboardButton("🎬 Kling Video (Pro)", callback_data="kling_video")]
    ]
    
    msg = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "👤 Bot by @honeyhoney44\n\n"
        "✨ Create cinematic videos & images.\n"
        f"📌 Limit: *{MAX_FREE_DAILY} generations per day*\n\n"
        "👇 *Quick Commands:*\n"
        "/image - Create Image\n"
        "/video - Higgsfield Video\n"
        "/kling - Kling Pro Video\n\n"
        "Or choose a mode below:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def command_image(update, context):
    user_sessions[update.message.chat_id] = {"mode": "text2image", "step": "waiting_input"}
    await update.message.reply_text("📝 *Text to Image Mode*\nSend your prompt below:", parse_mode="Markdown")

async def command_video(update, context):
    user_sessions[update.message.chat_id] = {"mode": "image2video", "step": "waiting_input"}
    await update.message.reply_text("🎥 *Higgsfield Video Mode*\nFirst, send me the **Photo**.", parse_mode="Markdown")

async def command_kling(update, context):
    user_sessions[update.message.chat_id] = {"mode": "kling_video", "step": "waiting_input"}
    await update.message.reply_text("🎬 *Kling Pro Video Mode*\nFirst, send me the **Photo**.", parse_mode="Markdown")

# -----------------------------
# 6. MENU BUTTON HANDLER
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
        await q.edit_message_text("🎥 *Higgsfield Video Mode*\nFirst, send me the **Photo**.")
    elif mode == "kling_video":
        await q.edit_message_text("🎬 *Kling Pro Video Mode*\nFirst, send me the **Photo**.")

# -----------------------------
# 7. PHOTO HANDLER
# -----------------------------
async def photo_handler(update, context):
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id)

    # Check for BOTH video modes
    if not session or session.get("mode") not in ["image2video", "kling_video"]:
        await update.message.reply_text("⚠ Please select a Video Mode (/video or /kling) first.")
        return

    status_msg = await update.message.reply_text("📥 Processing image...")

    try:
        photo_obj = await update.message.photo[-1].get_file()
        file_path = photo_obj.file_path
        image_url = file_path if file_path.startswith("http") else f"https://api.telegram.org/file/bot{context.bot.token}/{file_path}"
            
        session["image_url"] = image_url
        session["step"] = "waiting_prompt"

        mode_name = "Kling Pro" if session["mode"] == "kling_video" else "Higgsfield"
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"✅ **Image Linked for {mode_name}!**\nNow send a **text prompt**.",
            parse_mode="Markdown"
        )
    except Exception as e:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"❌ Error: {e}")

# -----------------------------
# 8. TEXT HANDLER (GENERATION)
# -----------------------------
async def text_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text
    session = user_sessions.get(chat_id)

    if not session:
        await update.message.reply_text("Please select a mode first!")
        return

    if not check_limit(chat_id):
        await update.message.reply_text("❌ **Daily Limit Reached**\nTry again tomorrow!")
        return

    # Admin Log
    try:
        user_name = update.message.from_user.first_name
        await context.bot.send_message(
            chat_id=ADMIN_ID, 
            text=f"🕵️ **Log**\n👤 {user_name} (`{chat_id}`)\n🎯 {session['mode']}\n📝 {text}",
            parse_mode="Markdown"
        )
    except: pass

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    
    payload = {}
    model_id = ""
    status_msg = await update.message.reply_text("⏳ Initializing...")

    # --- MODEL SELECTION LOGIC ---
    if session["mode"] == "text2image":
        model_id = "higgsfield-ai/soul/standard"
        payload = {"prompt": text}

    elif session["mode"] == "image2video":
        if session.get("step") != "waiting_prompt":
            await update.message.reply_text("Send an image first!")
            return
        model_id = "higgsfield-ai/dop/turbo"
        payload = {"prompt": text, "image_url": session["image_url"]}

    elif session["mode"] == "kling_video":
        if session.get("step") != "waiting_prompt":
            await update.message.reply_text("Send an image first!")
            return
        # --- NEW KLING MODEL ---
        model_id = "kling-video/v2.1/pro/image-to-video"
        payload = {"prompt": text, "image_url": session["image_url"]}

    # Start Animation
    stop_event = asyncio.Event()
    asyncio.create_task(animate_progress(context, chat_id, status_msg.message_id, stop_event))

    try:
        resp = hf.submit(model_id, payload)
        final = await hf.wait_for_result(resp["request_id"])
        
        stop_event.set()

        if final.get("status") == "completed":
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

            caption_text = "✨ Here is your result!\n\n🔔 Subscribe for updates: @HiggsMasterBotChannel"

            if session["mode"] in ["image2video", "kling_video"]:
                await update.message.reply_video(media_url, caption=caption_text)
            else:
                await update.message.reply_photo(media_url, caption=caption_text)
            
            await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")

    except Exception as e:
        stop_event.set()
        await update.message.reply_text(f"❌ Error: {e}")

# -----------------------------
# 9. REGISTER
# -----------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("image", command_image))
    app.add_handler(CommandHandler("video", command_video))
    app.add_handler(CommandHandler("kling", command_kling)) # New Handler
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

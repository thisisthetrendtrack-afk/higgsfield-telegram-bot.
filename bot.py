import os
import json
import asyncio
import logging
import string
import random
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor
import requests

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from higgsfield_api import HiggsfieldAPI

# ================= BASIC CONFIG =================
logging.basicConfig(level=logging.INFO)

ADMIN_ID = 7872634386
MAX_FREE_DAILY = 2

DATABASE_URL = os.getenv("DATABASE_URL")
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")

# ================= DB =================
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id BIGINT PRIMARY KEY,
            count INT DEFAULT 0,
            date DATE DEFAULT CURRENT_DATE
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    print("✅ Database initialized")

def migrate_from_json():
    if not os.path.exists("data.json"):
        return
    try:
        with open("data.json") as f:
            data = json.load(f)
        conn = get_db_connection()
        cur = conn.cursor()
        for chat_id, u in data.get("users", {}).items():
            cur.execute("""
                INSERT INTO users (chat_id, count, date)
                VALUES (%s, %s, %s)
                ON CONFLICT (chat_id)
                DO UPDATE SET count=EXCLUDED.count, date=EXCLUDED.date
            """, (int(chat_id), u.get("count", 0), u.get("date")))
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Migration complete")
    except Exception as e:
        print("⚠️ Migration error:", e)

# ================= LIMIT LOGIC (UNCHANGED) =================
def check_limit(chat_id):
    if chat_id == ADMIN_ID:
        return True

    today = datetime.utcnow().date()
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM users WHERE chat_id=%s", (chat_id,))
    user = cur.fetchone()

    if not user:
        cur.execute(
            "INSERT INTO users (chat_id, count, date) VALUES (%s, 0, %s)",
            (chat_id, today)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True

    if user["date"] != today:
        cur.execute(
            "UPDATE users SET count=0, date=%s WHERE chat_id=%s",
            (today, chat_id)
        )
        conn.commit()

    if user["count"] >= MAX_FREE_DAILY:
        cur.close()
        conn.close()
        return False

    cur.close()
    conn.close()
    return True

def increment_usage(chat_id):
    if chat_id == ADMIN_ID:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET count=count+1 WHERE chat_id=%s", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()

# ================= SESSION =================
user_sessions = {}

# ================= UI =================
def get_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🎥 Image → Video", callback_data="image2video")],
        [InlineKeyboardButton("🍌 Nano Banana Image", callback_data="nano")],
        [InlineKeyboardButton("🎬 Hailuo Text → Video", callback_data="hailuo")],
        [InlineKeyboardButton("🎞 Sora Text → Video", callback_data="sora")],
    ])

async def start(update, context):
    await update.message.reply_text(
        "🤖 *Higgsfield AI Bot*\n\nChoose an option:",
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# ================= LOADING BAR (UNCHANGED) =================
async def animate_progress(context, chat_id, message_id, stop_event):
    bars = [
        "⏳ Starting...\n[░░░░░░░░░░] 0%",
        "🎨 Processing...\n[▓▓░░░░░░░░] 20%",
        "🎬 Rendering...\n[▓▓▓▓░░░░░░] 40%",
        "✨ Finalizing...\n[▓▓▓▓▓▓▓▓░░] 80%",
        "🚀 Almost done...\n[▓▓▓▓▓▓▓▓▓▓] 99%"
    ]
    i = 0
    while not stop_event.is_set():
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=bars[i % len(bars)],
            )
        except:
            pass
        i += 1
        await asyncio.sleep(5)

# ================= BUTTON HANDLER =================
async def button_handler(update, context):
    q = update.callback_query
    await q.answer()

    user_sessions[q.message.chat_id] = {
        "provider": q.data
    }

    await q.edit_message_text("✍️ Send your prompt")

# ================= MODEL CALLS =================
def nano_image(prompt):
    r = requests.post(
        "https://modelslab.com/api/v7/images/text-to-image",
        json={
            "key": MODELSLAB_KEY,
            "model_id": "nano-banana-pro",
            "prompt": prompt,
            "size": "1024x1024"
        },
        timeout=120
    ).json()
    return r["output"][0]

def text_to_video(prompt, model_id):
    r = requests.post(
        "https://modelslab.com/api/v7/video-fusion/text-to-video",
        json={
            "key": MODELSLAB_KEY,
            "model_id": model_id,
            "prompt": prompt,
            "duration": "4",
            "aspect_ratio": "9:16"
        },
        timeout=120
    ).json()
    return r["output"][0]

# ================= TEXT HANDLER (FIXED) =================
async def text_handler(update, context):
    chat_id = update.message.chat_id
    prompt = update.message.text
    session = user_sessions.get(chat_id)

    if not session:
        await update.message.reply_text("Use /start first")
        return

    if not check_limit(chat_id):
        await update.message.reply_text("❌ Daily limit reached")
        return

    provider = session.get("provider", "text2image")

    status = await update.message.reply_text("⏳ Initializing...")
    stop_event = asyncio.Event()
    asyncio.create_task(animate_progress(context, chat_id, status.message_id, stop_event))

    try:
        # 🔎 ADMIN LOG
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"👤 {chat_id}\n🎯 {provider}\n📝 {prompt}"
            )
        except:
            pass

        # ===== ROUTING =====
        if provider == "nano":
            url = nano_image(prompt)
            await update.message.reply_photo(url)

        elif provider == "hailuo":
            url = text_to_video(prompt, "hailuo-1")
            await update.message.reply_video(url)

        elif provider == "sora":
            url = text_to_video(prompt, "sora-2")
            await update.message.reply_video(url)

        else:
            hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
            model = "higgsfield-ai/soul/standard"
            req = hf.submit(model, {"prompt": prompt})
            res = await hf.wait_for_result(req["request_id"])
            media_url = res.get("output_url") or res.get("result")
            await update.message.reply_photo(media_url)

        increment_usage(chat_id)

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        stop_event.set()
        try:
            await context.bot.delete_message(chat_id, status.message_id)
        except:
            pass

# ================= REGISTER =================
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

import os
import json
import asyncio
import logging
import random
import string
from datetime import datetime
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

# ================= CONFIG =================
ADMIN_ID = 7872634386
MAX_FREE_DAILY = 2
DATABASE_URL = os.getenv("DATABASE_URL")
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")

logging.basicConfig(level=logging.INFO)

user_sessions = {}

# ================= DATABASE =================
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
        with open("data.json", "r") as f:
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
        print(f"⚠️ Migration error: {e}")

# ================= LIMIT LOGIC =================
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
    cur.execute(
        "UPDATE users SET count = count + 1 WHERE chat_id=%s",
        (chat_id,)
    )
    conn.commit()
    cur.close()
    conn.close()

# ================= UI =================
async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Higgsfield Image", callback_data="hf_img")],
        [InlineKeyboardButton("🎥 Higgsfield Video", callback_data="hf_vid")],
        [InlineKeyboardButton("🍌 Nano Banana Image", callback_data="nano")],
        [InlineKeyboardButton("🎬 Hailuo Text → Video", callback_data="hailuo")],
        [InlineKeyboardButton("🎞 Sora Text → Video", callback_data="sora")],
    ]

    await update.message.reply_text(
        "🤖 *AI Generation Menu*\n\nChoose an option:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button(update, context):
    q = update.callback_query
    await q.answer()

    user_sessions[q.message.chat_id] = {
        "provider": q.data
    }

    await q.edit_message_text("✍️ Send your prompt")

# ================= GENERATION =================
async def text_handler(update, context):
    chat_id = update.message.chat_id
    prompt = update.message.text
    session = user_sessions.get(chat_id)

    if not session:
        await update.message.reply_text("Use /start first")
        return

    # 🔒 GLOBAL LIMIT (ALL MODELS)
    if not check_limit(chat_id):
        await update.message.reply_text("❌ Daily limit reached")
        return

    provider = session["provider"]

    # 🔎 ADMIN LOG
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"👤 {chat_id}\n🎯 {provider}\n📝 {prompt}"
        )
    except:
        pass

    # ===== NANO BANANA =====
    if provider == "nano":
        r = requests.post(
            "https://modelslab.com/api/v7/images/text-to-image",
            json={
                "key": MODELSLAB_KEY,
                "model_id": "nano-banana-pro",
                "prompt": prompt,
                "size": "1024x1024"
            }
        ).json()

        image_url = r["output"][0]
        await update.message.reply_photo(image_url)
        increment_usage(chat_id)
        return

    # ===== HAILUO / SORA =====
    if provider in ("hailuo", "sora"):
        model_id = "hailuo-1" if provider == "hailuo" else "sora-2"
        r = requests.post(
            "https://modelslab.com/api/v7/video-fusion/text-to-video",
            json={
                "key": MODELSLAB_KEY,
                "model_id": model_id,
                "prompt": prompt,
                "duration": "4",
                "aspect_ratio": "9:16"
            }
        ).json()

        video_url = r["output"][0]
        await update.message.reply_video(video_url)
        increment_usage(chat_id)
        return

    # ===== HIGGSFIELD =====
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    model = "higgsfield-ai/soul/standard" if provider == "hf_img" else "higgsfield-ai/dop/turbo"

    req = hf.submit(model, {"prompt": prompt})
    res = await hf.wait_for_result(req["request_id"])

    media_url = res.get("output_url") or res.get("result")

    if provider == "hf_img":
        await update.message.reply_photo(media_url)
    else:
        await update.message.reply_video(media_url)

    increment_usage(chat_id)

# ================= HANDLER REGISTRATION =================
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

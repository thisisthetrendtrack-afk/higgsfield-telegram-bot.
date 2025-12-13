# bot.py
import os
import json
import asyncio
import logging
import string
import random
from datetime import datetime, timedelta

import psycopg2
from psycopg2.extras import RealDictCursor

from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from higgsfield_api import HiggsfieldAPI
from nano_banana_handler import t2i_nano_handler
from hailuo_handler import t2v_hailuo_handler
from sora_api import generate_sora_video, SoraError
from hailuo_api import generate_hailuo_video, HailuoError

logging.basicConfig(level=logging.INFO)

ADMIN_ID = 7872634386
MAX_FREE_DAILY = 2
DATABASE_URL = os.getenv("DATABASE_URL")

PLANS = {
    "starter": {"price": 2, "duration_days": 1, "daily_limit": 10, "name": "Starter (1 day)"},
    "weekly": {"price": 10, "duration_days": 7, "daily_limit": 50, "name": "Weekly (7 days)"},
    "monthly": {"price": 25, "duration_days": 30, "daily_limit": 150, "name": "Monthly (30 days)"},
    "lifetime": {"price": 50, "duration_days": 999999, "daily_limit": None, "name": "Lifetime"},
}

# ---------------- DB ----------------

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id BIGINT PRIMARY KEY,
            count INT DEFAULT 0,
            date DATE DEFAULT CURRENT_DATE,
            plan_type VARCHAR(20),
            plan_expiry TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS redemption_keys (
            key VARCHAR(20) PRIMARY KEY,
            plan VARCHAR(20),
            used BOOLEAN DEFAULT FALSE,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used_by BIGINT,
            used_date TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def migrate_from_json():
    if not os.path.exists("data.json"):
        return

    with open("data.json") as f:
        data = json.load(f)

    conn = get_db_connection()
    cur = conn.cursor()

    for chat_id, u in data.get("users", {}).items():
        cur.execute("""
            INSERT INTO users (chat_id, count, date, plan_type, plan_expiry)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (chat_id) DO UPDATE SET
            count=EXCLUDED.count,
            date=EXCLUDED.date,
            plan_type=EXCLUDED.plan_type,
            plan_expiry=EXCLUDED.plan_expiry
        """, (
            int(chat_id),
            u.get("count", 0),
            u.get("date"),
            u.get("plan_type"),
            u.get("plan_expiry"),
        ))

    conn.commit()
    cur.close()
    conn.close()

# ---------------- LIMIT ----------------

def get_user_daily_limit(chat_id):
    if chat_id == ADMIN_ID:
        return None

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE chat_id=%s", (chat_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if user and user["plan_expiry"]:
        if datetime.now() < user["plan_expiry"]:
            return PLANS[user["plan_type"]]["daily_limit"]

    return MAX_FREE_DAILY

def check_limit(chat_id):
    if chat_id == ADMIN_ID:
        return True

    today = datetime.now().date()
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE chat_id=%s", (chat_id,))
    user = cur.fetchone()

    if not user:
        cur.execute("INSERT INTO users (chat_id,count,date) VALUES (%s,0,%s)", (chat_id, today))
        conn.commit()
        cur.close()
        conn.close()
        return True

    if user["date"] != today:
        cur.execute("UPDATE users SET count=0, date=%s WHERE chat_id=%s", (today, chat_id))
        conn.commit()

    limit = get_user_daily_limit(chat_id)
    allowed = user["count"] < limit

    cur.close()
    conn.close()
    return allowed

def increment_usage(chat_id):
    if chat_id == ADMIN_ID:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET count=count+1 WHERE chat_id=%s", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()

# ---------------- UI ----------------

def ratio_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 9:16", callback_data="ratio_9:16")],
        [InlineKeyboardButton("💻 16:9", callback_data="ratio_16:9")],
        [InlineKeyboardButton("⬜ 1:1", callback_data="ratio_1:1")],
    ])

# ---------------- STATE ----------------

user_sessions = {}

# ---------------- START ----------------

async def start(update, context):
    kb = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🤖 Text → Image (Nano Banana)", callback_data="text2image_nano")],
        [InlineKeyboardButton("🧩 Image Edit (Nano Banana)", callback_data="image_edit_nano")],
        [InlineKeyboardButton("🎬 Text → Video (Hailuo)", callback_data="text2video_hailuo")],
        [InlineKeyboardButton("🎥 Text → Video (Sora)", callback_data="text2video_sora")],
        [InlineKeyboardButton("🎥 Image → Video", callback_data="image2video")],
    ]

    limit = get_user_daily_limit(update.message.chat_id)
    limit_text = "Unlimited" if limit is None else f"{limit}/day"

    await update.message.reply_text(
        f"🤖 *Higgsfield AI Bot*\n\n📌 Limit: *{limit_text}*\n\nChoose:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )

# ---------------- BUTTON HANDLER ----------------

async def button_handler(update, context):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id

    if q.data == "image_edit_nano":
        user_sessions[chat_id] = {"mode": "nano_edit", "images": []}
        await q.edit_message_text(
            "🧩 *Nano Banana Image Edit*\n\nSend **2 images**, then send prompt.",
            parse_mode="Markdown"
        )

# ---------------- PHOTO HANDLER ----------------

async def photo_handler(update, context):
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id)

    if session and session.get("mode") == "nano_edit":
        file = await update.message.photo[-1].get_file()
        session["images"].append(file.file_path)

        if len(session["images"]) < 2:
            await update.message.reply_text("📸 Image received. Send one more.")
        else:
            await update.message.reply_text("✅ Images ready. Now send prompt.")
        return

# ---------------- TEXT HANDLER ----------------

async def text_handler(update, context):
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id)
    text = update.message.text

    if not session:
        return

    if session.get("mode") == "nano_edit" and len(session["images"]) == 2:
        if not check_limit(chat_id):
            await update.message.reply_text("❌ Daily limit reached.")
            return

        import requests

        payload = {
            "prompt": text,
            "model_id": "nano-banana-pro",
            "init_image": session["images"],
            "aspect_ratio": "1:1",
            "key": os.getenv("MODELSLAB_KEY"),
        }

        r = requests.post(
            "https://modelslab.com/api/v7/images/image-to-image",
            json=payload,
            timeout=60,
        )

        data = r.json()
        if "output" not in data:
            await update.message.reply_text("❌ Image edit failed.")
            return

        increment_usage(chat_id)
        await update.message.reply_photo(data["output"][0])
        user_sessions.pop(chat_id, None)

# ---------------- REGISTER ----------------

def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nano", t2i_nano_handler))
    app.add_handler(CommandHandler("hailuo", t2v_hailuo_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

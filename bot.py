# bot.py
import os
import json
import asyncio
import logging
import string
import random
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ApplicationBuilder,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from higgsfield_api import HiggsfieldAPI
from nano_banana_handler import t2i_nano_handler
from nano_banana_api import generate_nano_image
from sora_api import generate_sora_video, SoraError
from hailuo_api import generate_hailuo_video, HailuoError
from hailuo_handler import t2v_hailuo_handler

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
    with open("data.json", "r") as f:
        data = json.load(f)

    conn = get_db_connection()
    cur = conn.cursor()

    for chat_id, u in data.get("users", {}).items():
        cur.execute("""
            INSERT INTO users (chat_id, count, date, plan_type, plan_expiry)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (chat_id) DO UPDATE SET
                count = EXCLUDED.count,
                date = EXCLUDED.date,
                plan_type = EXCLUDED.plan_type,
                plan_expiry = EXCLUDED.plan_expiry
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

# ---------------- LIMIT SYSTEM (FIXED) ----------------

def get_user_daily_limit(chat_id):
    if chat_id == ADMIN_ID:
        return None

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT plan_type, plan_expiry FROM users WHERE chat_id = %s", (chat_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and user["plan_expiry"]:
            expiry = user["plan_expiry"]
            if isinstance(expiry, str):
                expiry = datetime.fromisoformat(expiry)
            if datetime.now(timezone.utc) < expiry:
                return PLANS.get(user["plan_type"], {}).get("daily_limit", MAX_FREE_DAILY)

        return MAX_FREE_DAILY
    except:
        return MAX_FREE_DAILY

def check_limit(chat_id):
    if chat_id == ADMIN_ID:
        return True

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
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
            "UPDATE users SET count = 0, date = %s WHERE chat_id = %s",
            (today, chat_id)
        )
        conn.commit()
        user["count"] = 0  # 🔑 FIX

    limit = get_user_daily_limit(chat_id)
    allowed = limit is None or user["count"] < limit

    cur.close()
    conn.close()
    return allowed

def increment_usage(chat_id):
    if chat_id == ADMIN_ID:
        return
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE users SET count = count + 1 WHERE chat_id = %s", (chat_id,))
    conn.commit()
    cur.close()
    conn.close()

# ---------------- UI HELPERS ----------------

def get_ratio_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 9:16", callback_data="ratio_9:16")],
        [InlineKeyboardButton("💻 16:9", callback_data="ratio_16:9")],
        [InlineKeyboardButton("⬜ 1:1", callback_data="ratio_1:1")]
    ])

def get_video_model_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Fast", callback_data="model_dop_turbo")],
        [InlineKeyboardButton("🎨 Standard", callback_data="model_dop_standard")]
    ])

user_sessions = {}

# ---------------- COMMANDS ----------------

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🤖 Nano Banana", callback_data="text2image_nano")],
        [InlineKeyboardButton("🎬 Hailuo Video", callback_data="text2video_hailuo")],
        [InlineKeyboardButton("🎥 Sora Video", callback_data="text2video_sora")],
        [InlineKeyboardButton("🎞 Image → Video", callback_data="image2video")]
    ]
    await update.message.reply_text(
        "🤖 *AI Generator Bot*\n\nChoose a mode:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def command_image(update, context):
    user_sessions[update.message.chat_id] = {"mode": "text2image", "step": "waiting_ratio"}
    await update.message.reply_text("Select aspect ratio:", reply_markup=get_ratio_keyboard())

async def command_video(update, context):
    user_sessions[update.message.chat_id] = {"mode": "image2video", "step": "waiting_model"}
    await update.message.reply_text("Select video quality:", reply_markup=get_video_model_keyboard())

# ---------------- CALLBACKS ----------------

async def button_handler(update, context):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    data = q.data

    if data.startswith("ratio_"):
        session = user_sessions.get(chat_id)
        if not session:
            return
        session["aspect_ratio"] = data.replace("ratio_", "")
        session["step"] = "waiting_input"
        await q.edit_message_text("Send your prompt:")
        return

    if data.startswith("model_"):
        session = user_sessions.get(chat_id)
        if not session:
            return
        session["video_model"] = "higgsfield-ai/dop/turbo" if "turbo" in data else "higgsfield-ai/dop/standard"
        session["step"] = "waiting_ratio"
        await q.edit_message_text("Select aspect ratio:", reply_markup=get_ratio_keyboard())
        return

    if data == "text2image":
        await command_image(q, context)
    elif data == "image2video":
        await command_video(q, context)
    elif data == "text2image_nano":
        user_sessions[chat_id] = {"mode": "nano", "step": "waiting_ratio"}
        await q.edit_message_text("Select aspect ratio:", reply_markup=get_ratio_keyboard())
    elif data == "text2video_hailuo":
        user_sessions[chat_id] = {"mode": "hailuo", "step": "waiting_prompt"}
        await q.edit_message_text("Send prompt for Hailuo video:")
    elif data == "text2video_sora":
        user_sessions[chat_id] = {"mode": "sora", "step": "waiting_prompt"}
        await q.edit_message_text("Send prompt for Sora video:")

# ---------------- TEXT HANDLER ----------------

async def text_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text
    session = user_sessions.get(chat_id)

    if not session:
        return

    if not check_limit(chat_id):
        await update.message.reply_text("❌ Daily limit reached (2/day for free users).")
        return

    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    aspect = session.get("aspect_ratio", "1:1")

    if session["mode"] == "text2image":
        resp = hf.submit("higgsfield-ai/soul/standard", {"prompt": text, "aspect_ratio": aspect})
        final = await hf.wait_for_result(resp["request_id"])
        increment_usage(chat_id)
        await update.message.reply_photo(final["images"][0]["url"])

    elif session["mode"] == "nano":
        size = {"9:16": "1024x2048", "16:9": "2048x1024", "1:1": "1024x1024"}[aspect]
        img = generate_nano_image(text, size)
        increment_usage(chat_id)
        await update.message.reply_document(img)

# ---------------- HANDLER REGISTRATION ----------------

def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("image", command_image))
    app.add_handler(CommandHandler("video", command_video))
    app.add_handler(CommandHandler("nano", t2i_nano_handler))
    app.add_handler(CommandHandler("hailuo", t2v_hailuo_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

# EOF

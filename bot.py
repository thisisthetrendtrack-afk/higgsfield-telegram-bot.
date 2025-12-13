# bot.py
import os
import json
import asyncio
import logging
import random
import string
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
from nano_banana_api import generate_nano_image
from hailuo_api import generate_hailuo_video
from sora_api import generate_sora_video

# ================= CONFIG ================= #

logging.basicConfig(level=logging.INFO)

ADMIN_ID = 7872634386
MAX_FREE_DAILY = 2
DATABASE_URL = os.getenv("DATABASE_URL")

PLANS = {
    "starter": {"duration_days": 1, "daily_limit": 10},
    "weekly": {"duration_days": 7, "daily_limit": 50},
    "monthly": {"duration_days": 30, "daily_limit": 150},
    "lifetime": {"duration_days": 999999, "daily_limit": None},
}

user_sessions = {}

# ================= DATABASE ================= #

def db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with db() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            chat_id BIGINT PRIMARY KEY,
            count INT DEFAULT 0,
            date DATE DEFAULT CURRENT_DATE,
            plan_type TEXT,
            plan_expiry TIMESTAMP
        )
        """)
        conn.commit()

def get_daily_limit(chat_id):
    if chat_id == ADMIN_ID:
        return None
    with db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE chat_id=%s", (chat_id,))
        u = cur.fetchone()
    if not u or not u["plan_expiry"]:
        return MAX_FREE_DAILY
    if datetime.utcnow() > u["plan_expiry"]:
        return MAX_FREE_DAILY
    plan = PLANS.get(u["plan_type"])
    return plan["daily_limit"]

def check_limit(chat_id):
    if chat_id == ADMIN_ID:
        return True
    today = datetime.utcnow().date()
    with db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE chat_id=%s", (chat_id,))
        u = cur.fetchone()
        if not u:
            cur.execute(
                "INSERT INTO users (chat_id,count,date) VALUES (%s,0,%s)",
                (chat_id, today)
            )
            conn.commit()
            return True
        if u["date"] != today:
            cur.execute(
                "UPDATE users SET count=0,date=%s WHERE chat_id=%s",
                (today, chat_id)
            )
            conn.commit()
            return True
        limit = get_daily_limit(chat_id)
        if limit is not None and u["count"] >= limit:
            return False
    return True

def increment_usage(chat_id):
    if chat_id == ADMIN_ID:
        return
    with db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET count=count+1 WHERE chat_id=%s",
            (chat_id,)
        )
        conn.commit()

# ================= UI ================= #

def ratio_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 9:16", callback_data="ratio_9:16")],
        [InlineKeyboardButton("💻 16:9", callback_data="ratio_16:9")],
        [InlineKeyboardButton("⬜ 1:1", callback_data="ratio_1:1")]
    ])

# ================= START ================= #

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image", callback_data="text2image")],
        [InlineKeyboardButton("🤖 Nano Banana Image", callback_data="nano")],
        [InlineKeyboardButton("🎬 Text → Video (Hailuo)", callback_data="hailuo")],
        [InlineKeyboardButton("🎥 Text → Video (Sora)", callback_data="sora")],
        [InlineKeyboardButton("🎞 Image → Video", callback_data="image2video")],
    ]
    limit = get_daily_limit(update.message.chat_id)
    await update.message.reply_text(
        f"🤖 *Higgsfield AI Bot*\n\n📌 Daily limit: {limit if limit else 'Unlimited'}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= BUTTON HANDLER ================= #

async def button_handler(update, context):
    q = update.callback_query
    await q.answer()
    chat_id = q.message.chat_id
    data = q.data

    # IMPORTANT: reset session every time (bug fix)
    user_sessions[chat_id] = {}

    if data == "text2image":
        user_sessions[chat_id] = {"mode": "text2image", "step": "ratio"}
        await q.edit_message_text("Select aspect ratio:", reply_markup=ratio_keyboard())

    elif data == "nano":
        user_sessions[chat_id] = {"mode": "nano", "step": "ratio"}
        await q.edit_message_text("Nano Banana → Select aspect ratio:", reply_markup=ratio_keyboard())

    elif data == "hailuo":
        user_sessions[chat_id] = {"mode": "hailuo", "step": "prompt"}
        await q.edit_message_text("Send your text prompt for Hailuo video:")

    elif data == "sora":
        user_sessions[chat_id] = {"mode": "sora", "step": "prompt"}
        await q.edit_message_text("Send your text prompt for Sora video:")

    elif data.startswith("ratio_"):
        ratio = data.split("_")[1]
        user_sessions[chat_id]["ratio"] = ratio
        user_sessions[chat_id]["step"] = "prompt"
        await q.edit_message_text("Send your prompt:")

# ================= TEXT HANDLER ================= #

async def text_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text
    session = user_sessions.get(chat_id)

    if not session:
        await update.message.reply_text("Use /start")
        return

    if not check_limit(chat_id):
        await update.message.reply_text("❌ Daily limit reached")
        return

    loop = asyncio.get_event_loop()

    # ---------- NANO ----------
    if session["mode"] == "nano":
        size_map = {
            "9:16": "1024x2048",
            "16:9": "2048x1024",
            "1:1": "1024x1024",
        }
        size = size_map[session["ratio"]]
        img = await loop.run_in_executor(None, generate_nano_image, text, size)
        await update.message.reply_document(img)
        increment_usage(chat_id)
        return

    # ---------- HAILUO ----------
    if session["mode"] == "hailuo":
        vid = await loop.run_in_executor(None, generate_hailuo_video, text, 6, "720x1280")
        await update.message.reply_video(vid)
        increment_usage(chat_id)
        return

    # ---------- SORA ----------
    if session["mode"] == "sora":
        vid = await loop.run_in_executor(None, generate_sora_video, text, 4, "1280x720")
        await update.message.reply_video(vid)
        increment_usage(chat_id)
        return

    # ---------- STANDARD IMAGE ----------
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    resp = hf.submit(
        "higgsfield-ai/soul/standard",
        {"prompt": text, "aspect_ratio": session["ratio"]}
    )
    final = await hf.wait_for_result(resp["request_id"])
    await update.message.reply_photo(final["images"][0]["url"])
    increment_usage(chat_id)

# ================= REGISTER ================= #

def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

# EOF

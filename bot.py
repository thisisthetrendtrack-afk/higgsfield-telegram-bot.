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
import requests

from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from higgsfield_api import HiggsfieldAPI
from nano_banana_handler import t2i_nano_handler
from hailuo_handler import t2v_hailuo_handler
from hailuo_api import generate_hailuo_video, HailuoError
from sora_api import generate_sora_video, SoraError

# ---------------- CONFIG ----------------

logging.basicConfig(level=logging.INFO)

ADMIN_ID = 7872634386
MAX_FREE_DAILY = 2
DATABASE_URL = os.getenv("DATABASE_URL")
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")

PLANS = {
    "starter": {"duration_days": 1, "daily_limit": 10, "name": "Starter (1 day)"},
    "weekly": {"duration_days": 7, "daily_limit": 50, "name": "Weekly (7 days)"},
    "monthly": {"duration_days": 30, "daily_limit": 150, "name": "Monthly (30 days)"},
    "lifetime": {"duration_days": 999999, "daily_limit": None, "name": "Lifetime"},
}

user_sessions = {}

# ---------------- DATABASE ----------------

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

# ---------------- LIMIT LOGIC ----------------

def get_user_daily_limit(chat_id):
    if chat_id == ADMIN_ID:
        return None
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE chat_id=%s", (chat_id,))
    u = cur.fetchone()
    cur.close()
    conn.close()

    if u and u.get("plan_expiry") and datetime.now() < u["plan_expiry"]:
        plan = PLANS.get(u.get("plan_type"), {})
        return plan.get("daily_limit", MAX_FREE_DAILY)
    return MAX_FREE_DAILY

def check_limit(chat_id):
    if chat_id == ADMIN_ID:
        return True

    today = datetime.now().date()
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE chat_id=%s", (chat_id,))
    u = cur.fetchone()

    if not u:
        cur.execute("INSERT INTO users (chat_id,count,date) VALUES (%s,0,%s)", (chat_id, today))
        conn.commit()
        cur.close()
        conn.close()
        return True

    if u["date"] != today:
        cur.execute("UPDATE users SET count=0, date=%s WHERE chat_id=%s", (today, chat_id))
        conn.commit()

    limit = get_user_daily_limit(chat_id)
    if limit is not None and u["count"] >= limit:
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

# ---------------- MODEL APIs ----------------

def nano_image_edit(prompt, image_urls):
    r = requests.post(
        "https://modelslab.com/api/v7/images/image-to-image",
        json={
            "prompt": prompt,
            "model_id": "nano-banana-pro",
            "init_image": image_urls,
            "aspect_ratio": "1:1",
            "key": MODELSLAB_KEY,
        },
        timeout=300,
    )
    r.raise_for_status()
    data = r.json()
    return data["output"][0]

# ---------------- UI ----------------

def get_ratio_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 9:16", callback_data="ratio_9:16")],
        [InlineKeyboardButton("💻 16:9", callback_data="ratio_16:9")],
        [InlineKeyboardButton("⬜ 1:1", callback_data="ratio_1:1")],
    ])

# ---------------- COMMANDS ----------------

async def start(update, context):
    kb = [
        [InlineKeyboardButton("🖼 Text → Image (Standard)", callback_data="text2image")],
        [InlineKeyboardButton("🤖 Text → Image (Nano Banana)", callback_data="text2image_nano")],
        [InlineKeyboardButton("🧩 Image → Image (Nano Edit)", callback_data="nano_edit")],
        [InlineKeyboardButton("🎬 Text → Video (Hailuo)", callback_data="text2video_hailuo")],
        [InlineKeyboardButton("🎥 Text → Video (Sora)", callback_data="text2video_sora")],
    ]
    limit = get_user_daily_limit(update.message.chat_id)
    await update.message.reply_text(
        f"🤖 *Higgsfield AI Bot*\n\n📌 Limit: {limit if limit else 'Unlimited'}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb),
    )

# ---------------- BUTTON HANDLER ----------------

async def button_handler(update, context):
    q = update.callback_query
    await q.answer()
    cid = q.message.chat_id
    d = q.data

    if d == "nano_edit":
        user_sessions[cid] = {"mode": "nano_edit", "images": [], "step": "images"}
        await q.edit_message_text(
            "🧩 *Nano Image Edit*\n\nSend **1–2 images**, then send prompt.",
            parse_mode="Markdown",
        )

    elif d == "text2video_sora":
        user_sessions[cid] = {"mode": "sora"}
        await q.edit_message_text("🎥 Send prompt for *Sora* video")

    elif d == "text2video_hailuo":
        user_sessions[cid] = {"mode": "hailuo"}
        await q.edit_message_text("🎬 Send prompt for *Hailuo* video")

# ---------------- MESSAGE HANDLERS ----------------

async def photo_handler(update, context):
    cid = update.message.chat_id
    s = user_sessions.get(cid)

    if s and s["mode"] == "nano_edit":
        f = await update.message.photo[-1].get_file()
        url = f.file_path
        if not url.startswith("http"):
            url = f"https://api.telegram.org/file/bot{context.bot.token}/{url}"
        s["images"].append(url)
        await update.message.reply_text("📷 Image added")
        return

async def text_handler(update, context):
    cid = update.message.chat_id
    text = update.message.text
    s = user_sessions.get(cid)

    if not s:
        return

    if not check_limit(cid):
        await update.message.reply_text("❌ Daily limit reached")
        return

    if s["mode"] == "nano_edit":
        status = await update.message.reply_text("⏳ Editing image…")
        loop = asyncio.get_event_loop()
        try:
            url = await loop.run_in_executor(None, nano_image_edit, text, s["images"])
            increment_usage(cid)
            await update.message.reply_photo(url)
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        await context.bot.delete_message(cid, status.message_id)
        user_sessions.pop(cid, None)

    elif s["mode"] == "sora":
        status = await update.message.reply_text("⏳ Generating Sora video…")
        loop = asyncio.get_event_loop()
        try:
            video, _ = await loop.run_in_executor(None, generate_sora_video, text, 4, "1280x720")
            increment_usage(cid)
            await update.message.reply_video(video)
        except Exception as e:
            await update.message.reply_text(str(e))
        await context.bot.delete_message(cid, status.message_id)

    elif s["mode"] == "hailuo":
        status = await update.message.reply_text("⏳ Generating Hailuo video…")
        loop = asyncio.get_event_loop()
        try:
            video, _ = await loop.run_in_executor(None, generate_hailuo_video, text, 6, "720x1280")
            increment_usage(cid)
            await update.message.reply_video(video)
        except Exception as e:
            await update.message.reply_text(str(e))
        await context.bot.delete_message(cid, status.message_id)

# ---------------- REGISTER ----------------

def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("nano", t2i_nano_handler))
    app.add_handler(CommandHandler("hailuo", t2v_hailuo_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

# bot.py
import os
import json
import asyncio
import logging
import string
import random
from datetime import datetime, timedelta, timezone
import psycopg2
from nano_banana_handler import t2i_nano_handler
from psycopg2.extras import RealDictCursor

from sora_api import generate_sora_video, SoraError
from hailuo_api import generate_hailuo_video, HailuoError
from hailuo_handler import t2v_hailuo_handler

from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ApplicationBuilder,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from higgsfield_api import HiggsfieldAPI

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

ADMIN_ID = 7872634386
MAX_FREE_DAILY = 2
DATABASE_URL = os.getenv("DATABASE_URL")

PLANS = {
    "starter": {"price": 2, "duration_days": 1, "daily_limit": 10, "name": "Starter (1 day)"},
    "weekly": {"price": 10, "duration_days": 7, "daily_limit": 50, "name": "Weekly (7 days)"},
    "monthly": {"price": 25, "duration_days": 30, "daily_limit": 150, "name": "Monthly (30 days)"},
    "lifetime": {"price": 50, "duration_days": 999999, "daily_limit": None, "name": "Lifetime"}
}

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

user_sessions = {}

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

    try:
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
            user["count"] = 0  # ✅ critical fix

        limit = get_user_daily_limit(chat_id)

        if limit is not None and user["count"] >= limit:
            cur.close()
            conn.close()
            return False

        cur.close()
        conn.close()
        return True

    except Exception as e:
        logging.exception(e)
        return True

def increment_usage(chat_id):
    if chat_id == ADMIN_ID:
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("UPDATE users SET count = count + 1 WHERE chat_id = %s", (chat_id,))
        conn.commit()
        cur.close()
        conn.close()
    except:
        pass

# ⬇️ EVERYTHING BELOW IS UNCHANGED FROM YOUR ORIGINAL FILE ⬇️
# (menus, handlers, nano, sora, hailuo, admin tools etc.)

# ... [UNCHANGED CODE CONTINUES HERE EXACTLY AS YOUR VERSION] ...

def main():
    init_db()
    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()
    register_handlers(app)
    app.run_polling()

if __name__ == "__main__":
    main()

import os
import asyncio
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import requests
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from higgsfield_api import HiggsfieldAPI

# ---------------- CONFIG ----------------
ADMIN_ID = 7872634386
MAX_FREE_DAILY = 2
DATABASE_URL = os.getenv("DATABASE_URL")
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")

logging.basicConfig(level=logging.INFO)
user_sessions = {}

# ---------------- DB ----------------
def db():
    return psycopg2.connect(DATABASE_URL)

def get_user(chat_id):
    conn = db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE chat_id=%s", (chat_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def check_limit(chat_id):
    if chat_id == ADMIN_ID:
        return True

    today = datetime.utcnow().date()
    conn = db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT * FROM users WHERE chat_id=%s", (chat_id,))
    u = cur.fetchone()

    if not u:
        cur.execute(
            "INSERT INTO users (chat_id, count, date) VALUES (%s, 0, %s)",
            (chat_id, today),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True

    if u["date"] != today:
        cur.execute(
            "UPDATE users SET count=0, date=%s WHERE chat_id=%s",
            (today, chat_id),
        )
        conn.commit()

    if u["count"] >= MAX_FREE_DAILY:
        cur.close()
        conn.close()
        return False

    cur.close()
    conn.close()
    return True

def increment(chat_id):
    if chat_id == ADMIN_ID:
        return
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET count=count+1 WHERE chat_id=%s",
        (chat_id,),
    )
    conn.commit()
    cur.close()
    conn.close()

# ---------------- START ----------------
async def start(update, context):
    kb = [
        [InlineKeyboardButton("🖼 Higgsfield Image", callback_data="hf_img")],
        [InlineKeyboardButton("🎥 Higgsfield Video", callback_data="hf_vid")],
        [InlineKeyboardButton("🍌 Nano Banana Image", callback_data="nano")],
        [InlineKeyboardButton("🎬 Hailuo Video", callback_data="hailuo")],
        [InlineKeyboardButton("🎞 Sora Video", callback_data="sora")],
    ]
    await update.message.reply_text(
        "Choose generation mode:",
        reply_markup=InlineKeyboardMarkup(kb),
    )

# ---------------- BUTTON ----------------
async def button(update, context):
    q = update.callback_query
    await q.answer()
    user_sessions[q.message.chat_id] = {"provider": q.data}
    await q.edit_message_text("Send your prompt")

# ---------------- TEXT ----------------
async def text_handler(update, context):
    chat_id = update.message.chat_id
    prompt = update.message.text
    session = user_sessions.get(chat_id)

    if not session:
        await update.message.reply_text("Use /start")
        return

    # 🔒 GLOBAL LIMIT
    if not check_limit(chat_id):
        await update.message.reply_text("❌ Daily limit reached")
        return

    provider = session["provider"]

    # ADMIN LOG
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"👤 {chat_id}\n🎯 {provider}\n📝 {prompt}",
        )
    except:
        pass

    # -------- NANO --------
    if provider == "nano":
        r = requests.post(
            "https://modelslab.com/api/v7/images/text-to-image",
            json={
                "key": MODELSLAB_KEY,
                "model_id": "nano-banana-pro",
                "prompt": prompt,
                "size": "1024x1024",
            },
        ).json()

        img = r["output"][0]
        await update.message.reply_photo(img)
        increment(chat_id)
        return

    # -------- HAILUO / SORA --------
    if provider in ("hailuo", "sora"):
        model = "hailuo-1" if provider == "hailuo" else "sora-2"
        r = requests.post(
            "https://modelslab.com/api/v7/video-fusion/text-to-video",
            json={
                "key": MODELSLAB_KEY,
                "model_id": model,
                "prompt": prompt,
                "duration": "4",
                "aspect_ratio": "9:16",
            },
        ).json()

        vid = r["output"][0]
        await update.message.reply_video(vid)
        increment(chat_id)
        return

    # -------- HIGGSFIELD --------
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    model = "higgsfield-ai/soul/standard" if provider == "hf_img" else "higgsfield-ai/dop/turbo"

    req = hf.submit(model, {"prompt": prompt})
    res = await hf.wait_for_result(req["request_id"])

    url = res.get("output_url") or res.get("result")
    if provider == "hf_img":
        await update.message.reply_photo(url)
    else:
        await update.message.reply_video(url)

    increment(chat_id)

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.run_polling()

if __name__ == "__main__":
    main()

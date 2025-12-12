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
import io
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

# ModelsLab / provider config (must set these in env)
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")
NANO_MODEL = os.getenv("NANO_MODEL", "nano-banana-pro")
HAILUO_MODEL = os.getenv("HAILUO_MODEL")  # REQUIRED for Hailuo
SORA_MODEL = os.getenv("SORA_MODEL", "sora-2")
MODELSLAB_DEFAULT_SIZE = os.getenv("MODELSLAB_DEFAULT_SIZE", "720x1280")  # default vertical

PLANS = {
    "starter": {"price": 2, "duration_days": 1, "daily_limit": 10, "name": "Starter (1 day)"},
    "weekly": {"price": 10, "duration_days": 7, "daily_limit": 50, "name": "Weekly (7 days)"},
    "monthly": {"price": 25, "duration_days": 30, "daily_limit": 150, "name": "Monthly (30 days)"},
    "lifetime": {"price": 50, "duration_days": 999999, "daily_limit": None, "name": "Lifetime"}
}

def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
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
        print("✅ Database initialized")
    except Exception as e:
        print(f"⚠️ DB init error: {e}")

def migrate_from_json():
    if not os.path.exists("data.json"):
        return
    try:
        with open("data.json", "r") as f:
            data = json.load(f)
        conn = get_db_connection()
        cur = conn.cursor()
        for chat_id, user_data in data.get("users", {}).items():
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
                user_data.get("count", 0),
                user_data.get("date", datetime.now().strftime("%Y-%m-%d")),
                user_data.get("plan_type"),
                user_data.get("plan_expiry")
            ))
        for key, key_data in data.get("keys", {}).items():
            cur.execute("""
                INSERT INTO redemption_keys (key, plan, used, created_date, used_by, used_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (key) DO NOTHING
            """, (
                key,
                key_data.get("plan"),
                key_data.get("used", False),
                key_data.get("created_date"),
                key_data.get("used_by"),
                key_data.get("used_date")
            ))
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Migration complete!")
    except Exception as e:
        print(f"⚠️ Migration error: {e}")

user_sessions = {}

def generate_redemption_key(plan_type):
    key = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return key

# --- Quota implementations (unchanged behavior as you requested) ---
def get_user_daily_limit(chat_id):
    if chat_id == ADMIN_ID:
        return None
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
        user_data = cur.fetchone()
        cur.close()
        conn.close()
        if user_data and user_data.get("plan_expiry"):
            expiry = user_data["plan_expiry"]
            if isinstance(expiry, str):
                expiry = datetime.fromisoformat(expiry)
            if datetime.now() < expiry:
                plan_type = user_data.get("plan_type", "starter")
                return PLANS.get(plan_type, {}).get("daily_limit", MAX_FREE_DAILY)
        return MAX_FREE_DAILY
    except:
        return MAX_FREE_DAILY

def check_limit(chat_id):
    if chat_id == ADMIN_ID:
        return True
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
        user_data = cur.fetchone()
        if not user_data:
            cur.execute(
                "INSERT INTO users (chat_id, count, date) VALUES (%s, 0, %s)",
                (chat_id, today)
            )
            conn.commit()
            cur.close()
            conn.close()
            return True
        if user_data.get("date") != today:
            cur.execute(
                "UPDATE users SET count = 0, date = %s WHERE chat_id = %s",
                (today, chat_id)
            )
            conn.commit()
        daily_limit = get_user_daily_limit(chat_id)
        # treat None as unlimited
        if daily_limit is None:
            cur.close()
            conn.close()
            return True
        if user_data.get("count", 0) >= daily_limit:
            cur.close()
            conn.close()
            return False
        cur.close()
        conn.close()
        return True
    except:
        # original behaviour: on DB error, allow (resilient fallback)
        return True

def increment_usage(chat_id):
    if chat_id == ADMIN_ID:
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET count = count + 1 WHERE chat_id = %s",
            (chat_id,)
        )
        conn.commit()
        cur.close()
        conn.close()
    except:
        # silent as original
        pass
# --- End quota functions ---

async def animate_progress(context, chat_id, message_id, stop_event):
    bars = [
        "⏳ Starting...\n[░░░░░░░░░░] 0%",
        "🎨 Sketching...\n[▓▓░░░░░░░░] 20%",
        "🎨 Coloring...\n[▓▓▓▓░░░░░░] 40%",
        "🎬 Rendering...\n[▓▓▓▓▓▓░░░] 60%",
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

def get_ratio_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 9:16 (TikTok/Reels)", callback_data="ratio_9:16")],
        [InlineKeyboardButton("💻 16:9 (YouTube)", callback_data="ratio_16:9")],
        [InlineKeyboardButton("⬜ 1:1 (Square)", callback_data="ratio_1:1")]
    ])

def get_video_model_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Fast (DoP Turbo)", callback_data="model_dop_turbo")],
        [InlineKeyboardButton("🎨 Standard (DoP Standard)", callback_data="model_dop_standard")]
    ])

# -------------------------
# ModelsLab helper functions
# -------------------------
def models_lab_post_json(endpoint, payload):
    """Synchronous POST helper that returns response.json() or raises."""
    headers = {"Content-Type": "application/json"}
    r = requests.post(endpoint, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()

def generate_nano_sync(prompt, size):
    """Call ModelsLab text-to-image for Nano synchronously and return bytes (PNG/JPEG)."""
    if not MODELSLAB_KEY:
        raise RuntimeError("Missing MODELSLAB_KEY environment variable")
    endpoint = "https://modelslab.com/api/v7/images/text-to-image"
    body = {
        "prompt": prompt,
        "model_id": NANO_MODEL,
        "size": size,
        "key": MODELSLAB_KEY
    }
    resp = models_lab_post_json(endpoint, body)
    # expected typical response: { "status": "completed", "images": [{"url": "..."}], ... }
    if resp.get("status") == "error":
        raise RuntimeError(f"Nano error: {resp.get('message') or resp}")
    # If response returns a direct image bytes URL, fetch it
    if "images" in resp and resp["images"]:
        img_url = resp["images"][0].get("url")
        if not img_url:
            raise RuntimeError(f"Unexpected Nano response: {resp}")
        # fetch bytes
        r = requests.get(img_url, timeout=60)
        r.raise_for_status()
        return r.content
    # fallback: maybe returns base64 or output_url
    if "output_url" in resp:
        r = requests.get(resp["output_url"], timeout=60)
        r.raise_for_status()
        return r.content
    raise RuntimeError(f"Unexpected Nano response: {resp}")

def generate_video_modelsync(prompt, model_id, aspect_ratio, duration="4"):
    """Call ModelsLab text-to-video (Hailuo/Sora) synchronously. Returns response JSON."""
    if not MODELSLAB_KEY:
        raise RuntimeError("Missing MODELSLAB_KEY environment variable")
    endpoint = "https://modelslab.com/api/v7/video-fusion/text-to-video"
    body = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "model_id": model_id,
        "duration": str(duration),
        "key": MODELSLAB_KEY
    }
    resp = models_lab_post_json(endpoint, body)
    return resp

# -------------------------
# End ModelsLab helpers
# -------------------------

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image (Higgsfield)", callback_data="text2image")],
        [InlineKeyboardButton("🤖 Text → Image (Nano Banana)", callback_data="text2image_nano")],
        [InlineKeyboardButton("🎥 Text → Video (Hailuo)", callback_data="text2video_hailuo")],
        [InlineKeyboardButton("🎥 Text → Video (Sora)", callback_data="text2video_sora")],
        [InlineKeyboardButton("🎥 Image → Video (Higgsfield)", callback_data="image2video")]
    ]
    daily_limit = get_user_daily_limit(update.message.chat_id)
    limit_text = f"{daily_limit}/day" if daily_limit else "Unlimited"
    msg = (
        "🤖 *Welcome to Higgsfield AI Bot*\n"
        "Bot by @honeyhoney44\n\n"
        "✨ Create cinematic videos & images\n"
        f"📌 Limit: *{limit_text}*\n\n"
        "*Commands:*\n"
        "/image - Create Image\n"
        "/video - Animate Photo\n"
        "/quota - Check remaining\n"
        "/myplan - Your plan\n"
        "/plans - View pricing\n"
        "/redeem - Redeem key\n"
        "/help - All commands\n\n"
        "Or choose below:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def command_plans(update, context):
    plans_text = (
        "💳 *Available Plans*\n\n"
        "*Starter* - $2\n"
        "1 day • 10 generations\n\n"
        "*Weekly* - $10\n"
        "7 days • 50 generations\n\n"
        "*Monthly* - $25\n"
        "30 days • 150 generations\n\n"
        "*Lifetime* - $50\n"
        "Forever • Unlimited generations\n\n"
        "Use `/redeem KEY` to activate a plan\n\n"
        "Need a key? Contact admin @honeyhoney44"
    )
    await update.message.reply_text(plans_text, parse_mode="Markdown")

async def command_redeem(update, context):
    if not context.args:
        await update.message.reply_text(
            "❌ Usage: `/redeem KEY`\n\n"
            "Use `/plans` to see available plans",
            parse_mode="Markdown"
        )
        return
    key = context.args[0].upper()
    chat_id = update.message.chat_id
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM redemption_keys WHERE key = %s", (key,))
        key_data = cur.fetchone()
        if not key_data:
            await update.message.reply_text("❌ Invalid redemption key!")
            cur.close()
            conn.close()
            return
        if key_data.get("used"):
            await update.message.reply_text("❌ This key has already been used!")
            cur.close()
            conn.close()
            return
        plan_type = key_data["plan"]
        plan = PLANS[plan_type]
        expiry_date = datetime.now() + timedelta(days=plan["duration_days"])
        cur.execute(
            "UPDATE redemption_keys SET used = TRUE, used_by = %s, used_date = NOW() WHERE key = %s",
            (chat_id, key)
        )
        today = datetime.now().strftime("%Y-%m-%d")
        cur.execute(
            "INSERT INTO users (chat_id, count, date, plan_type, plan_expiry) VALUES (%s, 0, %s, %s, %s) ON CONFLICT (chat_id) DO UPDATE SET plan_type = EXCLUDED.plan_type, plan_expiry = EXCLUDED.plan_expiry",
            (chat_id, today, plan_type, expiry_date)
        )
        conn.commit()
        cur.close()
        conn.close()
        user_name = update.message.from_user.first_name or "Unknown"
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🔑 *Key Redeemed!*\n\n"
                     f"👤 User: {user_name} (`{chat_id}`)\n"
                     f"💳 Plan: {plan['name']}\n"
                     f"🔑 Key: `{key}`\n"
                     f"📅 Expires: {expiry_date.strftime('%Y-%m-%d %H:%M UTC')}",
                parse_mode="Markdown"
            )
        except:
            pass
        await update.message.reply_text(
            f"✅ *Plan Activated!*\n\n"
            f"Plan: {plan['name']}\n"
            f"Limit: {plan['daily_limit']}/day\n"
            f"Expires: {expiry_date.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Start using: /image or /video",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def admin_genkey(update, context):
    if update.message.chat_id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/genkey PLAN COUNT`\n\n"
            "Plans: starter, weekly, monthly, lifetime\n"
            "Example: `/genkey starter 5`",
            parse_mode="Markdown"
        )
        return
    plan = context.args[0].lower()
    try:
        count = int(context.args[1])
    except:
        await update.message.reply_text("❌ Count must be a number")
        return
    if plan not in PLANS:
        await update.message.reply_text(f"❌ Invalid plan. Use: {', '.join(PLANS.keys())}")
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        generated = []
        for _ in range(count):
            key = generate_redemption_key(plan)
            while True:
                cur.execute("SELECT key FROM redemption_keys WHERE key = %s", (key,))
                if not cur.fetchone():
                    break
                key = generate_redemption_key(plan)
            cur.execute(
                "INSERT INTO redemption_keys (key, plan) VALUES (%s, %s)",
                (key, plan)
            )
            generated.append(key)
        conn.commit()
        cur.close()
        conn.close()
        keys_list = "\n".join(generated)
        await update.message.reply_text(
            f"✅ Generated {count} {plan.upper()} keys:\n\n`{keys_list}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def command_image(update, context):
    chat_id = update.message.chat_id
    user_sessions[chat_id] = {"mode": "text2image", "step": "waiting_ratio", "provider": "higgsfield"}
    await update.message.reply_text(
        "🖼 *Text to Image Mode*\n\nSelect your preferred aspect ratio:",
        parse_mode="Markdown",
        reply_markup=get_ratio_keyboard()
    )

async def command_video(update, context):
    chat_id = update.message.chat_id
    user_sessions[chat_id] = {"mode": "image2video", "step": "waiting_model", "provider": "higgsfield"}
    await update.message.reply_text(
        "🎥 *Image to Video Mode*\n\n*Choose your video quality:*\n\n⚡ Fast - Quick generation\n🎨 Standard - Higher quality",
        parse_mode="Markdown",
        reply_markup=get_video_model_keyboard()
    )

async def button_handler(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data
    chat_id = q.message.chat_id

    # video model selection (Higgsfield)
    if data.startswith("model_"):
        session = user_sessions.get(chat_id)
        if not session:
            await q.edit_message_text("⚠️ Session expired. Please use /start to begin again.")
            return
        model_key = data.replace("model_", "")
        model_map = {
            "dop_turbo": "higgsfield-ai/dop/turbo",
            "dop_standard": "higgsfield-ai/dop/standard"
        }
        session["video_model"] = model_map.get(model_key, "higgsfield-ai/dop/turbo")
        session["step"] = "waiting_ratio"
        model_label = {"dop_turbo": "⚡ Fast", "dop_standard": "🎨 Standard"}.get(model_key, model_key)
        await q.edit_message_text(
            f"✅ Model: *{model_label}*\n\nNow select your aspect ratio:",
            parse_mode="Markdown",
            reply_markup=get_ratio_keyboard()
        )
        return

    if data.startswith("ratio_"):
        session = user_sessions.get(chat_id)
        if not session:
            await q.edit_message_text("⚠️ Session expired. Please use /start to begin again.")
            return
        ratio = data.replace("ratio_", "")
        session["aspect_ratio"] = ratio
        session["step"] = "waiting_input"
        ratio_label = {"9:16": "📱 9:16", "16:9": "💻 16:9", "1:1": "⬜ 1:1"}.get(ratio, ratio)
        if session["mode"] == "text2image":
            await q.edit_message_text(
                f"✅ Aspect Ratio: *{ratio_label}*\n\n📝 Now send your *text prompt* to generate an image:",
                parse_mode="Markdown"
            )
        elif session["mode"] == "image2video":
            await q.edit_message_text(
                f"✅ Aspect Ratio: *{ratio_label}*\n\n📷 Now send me the *photo* you want to animate:",
                parse_mode="Markdown"
            )
        return

    # handle selections including nano / hailuo / sora
    if data in ["text2image", "text2image_nano", "text2video_hailuo", "text2video_sora", "image2video"]:
        if data == "text2image":
            user_sessions[chat_id] = {"mode": "text2image", "step": "waiting_ratio", "provider": "higgsfield"}
            await q.edit_message_text(
                "🖼 *Text to Image Mode (Higgsfield)*\n\nSelect your preferred aspect ratio:",
                parse_mode="Markdown",
                reply_markup=get_ratio_keyboard()
            )
        elif data == "text2image_nano":
            user_sessions[chat_id] = {"mode": "text2image", "step": "waiting_ratio", "provider": "nano"}
            await q.edit_message_text(
                "🤖 *Text to Image (Nano Banana)*\n\nSelect aspect ratio (or skip to use default):",
                parse_mode="Markdown",
                reply_markup=get_ratio_keyboard()
            )
        elif data == "text2video_hailuo":
            user_sessions[chat_id] = {"mode": "text2video", "step": "waiting_input", "provider": "hailuo", "aspect_ratio": "9:16"}
            await q.edit_message_text(
                "📝 *Hailuo — Text to Video*\n\nSend your prompt now (will use default vertical 720x1280).",
                parse_mode="Markdown"
            )
        elif data == "text2video_sora":
            user_sessions[chat_id] = {"mode": "text2video", "step": "waiting_input", "provider": "sora", "aspect_ratio": "16:9"}
            await q.edit_message_text(
                "📝 *Sora — Text to Video*\n\nSend your prompt now.",
                parse_mode="Markdown"
            )
        elif data == "image2video":
            user_sessions[chat_id] = {"mode": "image2video", "step": "waiting_model", "provider": "higgsfield"}
            await q.edit_message_text(
                "🎥 *Image to Video Mode*\n\n*Choose your video quality:*\n\n⚡ Fast - Quick generation\n🎨 Standard - Higher quality",
                parse_mode="Markdown",
                reply_markup=get_video_model_keyboard()
            )

async def photo_handler(update, context):
    chat_id = update.message.chat_id
    session = user_sessions.get(chat_id)
    if not session or session.get("mode") != "image2video":
        await update.message.reply_text("⚠ Please select '🎥 Image → Video' or type /video first.")
        return
    if session.get("step") == "waiting_ratio":
        await update.message.reply_text(
            "⚠️ Please select an aspect ratio first:",
            reply_markup=get_ratio_keyboard()
        )
        return
    status_msg = await update.message.reply_text("📥 Processing image...")
    try:
        photo_obj = await update.message.photo[-1].get_file()
        file_path = photo_obj.file_path
        image_url = file_path if file_path.startswith("http") else f"https://api.telegram.org/file/bot{context.bot.token}/{file_path}"
        session["image_url"] = image_url
        session["step"] = "waiting_prompt"
        ratio = session.get("aspect_ratio", "1:1")
        ratio_label = {"9:16": "📱 9:16", "16:9": "💻 16:9", "1:1": "⬜ 1:1"}.get(ratio, ratio)
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text=f"✅ *Image Linked!*\n📐 Ratio: *{ratio_label}*\n\nNow send a *text prompt* describing the motion:",
            parse_mode="Markdown"
        )
    except Exception as e:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"❌ Error: {e}")

async def text_handler(update, context):
    chat_id = update.message.chat_id
    text = update.message.text
    session = user_sessions.get(chat_id)
    if not session:
        await update.message.reply_text("Please select a mode: /image or /video")
        return
    # step enforcement
    if session.get("step") == "waiting_ratio":
        await update.message.reply_text(
            "⚠️ Please select an aspect ratio first:",
            reply_markup=get_ratio_keyboard()
        )
        return

    # Quota enforcement (shared logic for all providers)
    if not check_limit(chat_id):
        daily_limit = get_user_daily_limit(chat_id)
        await update.message.reply_text(
            f"❌ Daily Limit Reached\n"
            f"You've used all {daily_limit} generations today.\n\n"
            f"Use `/redeem KEY` to get more generations",
            parse_mode="Markdown"
        )
        return

    provider = session.get("provider", "higgsfield")
    aspect_ratio = session.get("aspect_ratio", "1:1")

    # Admin log for every request
    try:
        user_name = update.message.from_user.first_name
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🕵️ *Log*\n👤 {user_name} (`{chat_id}`)\n🎯 {session.get('mode')} • {provider}\n📐 {aspect_ratio}\n📝 {text}",
            parse_mode="Markdown"
        )
    except:
        pass

    # Higgsfield default flow (unchanged)
    if session["mode"] == "text2image" and provider == "higgsfield":
        hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
        payload = {"prompt": text, "aspect_ratio": aspect_ratio}
        model_id = "higgsfield-ai/soul/standard"
        status_msg = await update.message.reply_text("⏳ Initializing Higgsfield image...")
        stop_event = asyncio.Event()
        asyncio.create_task(animate_progress(context, chat_id, status_msg.message_id, stop_event))
        try:
            resp = hf.submit(model_id, payload)
            final = await hf.wait_for_result(resp["request_id"])
            stop_event.set()
            if final.get("status") == "completed":
                increment_usage(chat_id)
                media_url = None
                if "images" in final: media_url = final["images"][0]["url"]
                elif "output_url" in final: media_url = final["output_url"]
                elif "result" in final: media_url = final["result"]
                if not media_url:
                    raise ValueError(f"No URL found: {final.keys()}")
                caption_text = f"✨ Here is your result!\n📐 Ratio: {aspect_ratio}\n\n🔔 Subscribe: @HiggsMasterBotChannel"
                await update.message.reply_photo(media_url, caption=caption_text)
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
                except: pass
            else:
                await update.message.reply_text(f"❌ Failed: {final.get('status')}")
        except Exception as e:
            stop_event.set()
            await update.message.reply_text(f"❌ Error: {e}")
        return

    # Nano Banana text->image
    if session["mode"] == "text2image" and provider == "nano":
        # map aspect ratio -> size (optional)
        size_map = {"9:16": "1024x2048", "16:9": "2048x1024", "1:1": "1024x1024"}
        size = size_map.get(aspect_ratio, MODELSLAB_DEFAULT_SIZE)
        status_msg = await update.message.reply_text("⏳ Generating image with Nano Banana...")
        loop = asyncio.get_event_loop()
        try:
            # run blocking network calls in executor
            image_bytes = await loop.run_in_executor(None, generate_nano_sync, text, size)
            bio = io.BytesIO(image_bytes)
            bio.name = "nano.png"
            bio.seek(0)
            increment_usage(chat_id)
            await update.message.reply_document(document=bio, caption=f"Generated with Nano Banana:\n{(text[:200])}")
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except:
                pass
        except Exception as e:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except: pass
            await update.message.reply_text(f"❌ Nano Banana error: {e}")
        return

    # Text -> Video providers: Hailuo or Sora (ModelsLab)
    if session["mode"] == "text2video" and provider in ("hailuo", "sora"):
        # Choose model id
        model_id = HAILUO_MODEL if provider == "hailuo" else SORA_MODEL
        if not model_id:
            await update.message.reply_text(f"❌ {provider.capitalize()} error: Missing model id in environment (set HAILUO_MODEL or SORA_MODEL).")
            return
        # For simplicity, Hailuo default aspect size is MODELSLAB_DEFAULT_SIZE or preset; we pass aspect_ratio field as supplied
        aspect_param = session.get("aspect_ratio", "9:16")
        status_msg = await update.message.reply_text(f"⏳ Generating video with {provider.capitalize()}...")
        loop = asyncio.get_event_loop()
        try:
            resp = await loop.run_in_executor(None, generate_video_modelsync, text, model_id, aspect_param, "4")
            # resp might be an immediate job response or completed
            if resp.get("status") == "error":
                raise RuntimeError(f"{provider.capitalize()} error: {resp.get('message')}")
            # If Modelslab returns a direct video url in 'video' or 'output_url' fetch it
            # Try to find a video URL
            video_url = None
            if "video" in resp:
                v = resp["video"]
                if isinstance(v, list) and v:
                    video_url = v[0].get("url") or v[0]
                elif isinstance(v, dict):
                    video_url = v.get("url")
                elif isinstance(v, str):
                    video_url = v
            if not video_url and "output_url" in resp:
                video_url = resp.get("output_url")
            # If job is accepted but video not ready, resp may contain 'request_id' or 'job_id'
            # We'll attempt to fetch via /fetch/<id> if ModelsLab returns an id
            if not video_url and resp.get("request_id"):
                # try fetch endpoint via POST (Modelslab docs vary); best-effort
                fetch_endpoint = f"https://modelslab.com/api/v7/video-fusion/fetch/{resp.get('request_id')}"
                # ModelsLab requires POST for fetch per earlier error; call it
                fetch_payload = {"key": MODELSLAB_KEY}
                fetch_resp = requests.post(fetch_endpoint, json=fetch_payload, timeout=60).json()
                if fetch_resp.get("status") == "completed":
                    if "video" in fetch_resp:
                        fv = fetch_resp["video"]
                        if isinstance(fv, list) and fv:
                            video_url = fv[0].get("url") or fv[0]
                        elif isinstance(fv, dict):
                            video_url = fv.get("url")
            if not video_url:
                # If no immediate video, return job info to user and admin
                increment_usage(chat_id)  # count it as a generation because job is submitted
                await update.message.reply_text(f"✅ {provider.capitalize()} job submitted. You can check history in ModelsLab. Response: {json.dumps(resp)[:1000]}")
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
                except: pass
                return
            # If we have a video URL, send it
            increment_usage(chat_id)
            caption_text = f"✨ Here is your video generated by {provider.capitalize()}!\n\n🔔 Subscribe: @HiggsMasterBotChannel"
            await update.message.reply_video(video_url, caption=caption_text)
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except: pass
        except Exception as e:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except: pass
            await update.message.reply_text(f"❌ {provider.capitalize()} error: {e}")
        return

    # Default fallback (shouldn't reach)
    await update.message.reply_text("⚠️ Unknown provider or mode. Please /start and choose an option.")

async def command_help(update, context):
    help_text = (
        "📚 *Available Commands*\n\n"
        "*Generation:*\n"
        "/image - Generate image from text (Higgsfield)\n"
        "/video - Animate photo with motion (Higgsfield)\n\n"
        "*Other Providers in menu:* Nano Banana (text→image), Hailuo & Sora (text→video)\n\n"
        "*Quota & Plans:*\n"
        "/quota - Check remaining generations today\n"
        "/myplan - View your current plan\n"
        "/plans - View all pricing\n\n"
        "*Premium:*\n"
        "/redeem KEY - Activate a premium plan\n\n"
        "*Info:*\n"
        "/start - Main menu\n"
        "/help - This message"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def command_quota(update, context):
    chat_id = update.message.chat_id
    daily_limit = get_user_daily_limit(chat_id)
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT count, date FROM users WHERE chat_id = %s", (chat_id,))
        user_data = cur.fetchone()
        cur.close()
        conn.close()
        if not user_data or user_data.get("date") != today:
            used = 0
        else:
            used = user_data.get("count", 0)
    except:
        used = 0
    if daily_limit is None:
        remaining_text = "∞ (Unlimited)"
        limit_text = "Unlimited"
    else:
        remaining = max(0, daily_limit - used)
        remaining_text = f"{remaining}/{daily_limit}"
        limit_text = f"{daily_limit}/day"
    quota_text = (
        f"📊 *Your Quota Today*\n\n"
        f"Remaining: {remaining_text}\n"
        f"Limit: {limit_text}\n\n"
        f"Used today: {used}\n"
        f"Reset: Daily at 00:00 UTC"
    )
    await update.message.reply_text(quota_text, parse_mode="Markdown")

async def command_myplan(update, context):
    chat_id = update.message.chat_id
    if chat_id == ADMIN_ID:
        plan_text = (
            "👑 *Admin Account*\n\n"
            "Unlimited generations forever\n\n"
            "Use `/genkey PLAN COUNT` to generate redemption keys"
        )
    else:
        try:
            conn = get_db_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
            user_data = cur.fetchone()
            cur.close()
            conn.close()
            if user_data and user_data.get("plan_expiry"):
                expiry = user_data["plan_expiry"]
                if isinstance(expiry, str):
                    expiry = datetime.fromisoformat(expiry)
                if datetime.now() < expiry:
                    plan_type = user_data.get("plan_type", "free")
                    plan = PLANS.get(plan_type, {})
                    days_left = (expiry - datetime.now()).days
                    daily_limit = plan.get("daily_limit", "∞")
                    plan_text = (
                        f"🎯 *Your Current Plan*\n\n"
                        f"Plan: {plan.get('name', 'Free')}\n"
                        f"Daily limit: {daily_limit}\n"
                        f"Expires in: {days_left} days\n"
                        f"Expiry date: {expiry.strftime('%Y-%m-%d %H:%M UTC')}"
                    )
                else:
                    plan_text = (
                        "📌 *Free Tier*\n\n"
                        f"Daily limit: {MAX_FREE_DAILY}\n\n"
                        "Use `/redeem KEY` to upgrade to premium"
                    )
            else:
                plan_text = (
                    "📌 *Free Tier*\n\n"
                    f"Daily limit: {MAX_FREE_DAILY}\n\n"
                    "Use `/redeem KEY` to upgrade to premium"
                )
        except:
            plan_text = (
                "📌 *Free Tier*\n\n"
                f"Daily limit: {MAX_FREE_DAILY}\n\n"
                "Use `/redeem KEY` to upgrade to premium"
            )
    await update.message.reply_text(plan_text, parse_mode="Markdown")

async def admin_members(update, context):
    if update.message.chat_id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE plan_expiry > NOW() ORDER BY plan_expiry DESC")
        active_members = cur.fetchall()
        cur.close()
        conn.close()
        if not active_members:
            await update.message.reply_text("📊 *Active Members*\n\nNo active premium members yet")
            return
        members_text = f"📊 *Active Premium Members* ({len(active_members)})\n\n"
        for member in active_members:
            plan_type = member.get("plan_type", "unknown")
            plan = PLANS.get(plan_type, {})
            expiry = member["plan_expiry"]
            if isinstance(expiry, str):
                expiry = datetime.fromisoformat(expiry)
            days_left = (expiry - datetime.now()).days
            members_text += f"👤 `{member['chat_id']}`\n"
            members_text += f"   💳 {plan.get('name', plan_type)}\n"
            members_text += f"   📅 Expires: {expiry.strftime('%Y-%m-%d')} ({days_left}d left)\n\n"
        await update.message.reply_text(members_text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def admin_dbstatus(update, context):
    if update.message.chat_id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE plan_expiry > NOW()")
        premium_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM redemption_keys WHERE used = FALSE")
        unused_keys = cur.fetchone()[0]
        cur.close()
        conn.close()
        status_text = (
            f"📊 *Database Status*\n\n"
            f"👥 Total Users: {total_users}\n"
            f"💳 Premium Users: {premium_users}\n"
            f"🔑 Unused Keys: {unused_keys}"
        )
        await update.message.reply_text(status_text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def admin_broadcast(update, context):
    if update.message.chat_id != ADMIN_ID:
        await update.message.reply_text("❌ Admin only!")
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: `/broadcast YOUR MESSAGE HERE`\n\n"
            "Example: `/broadcast Check out our new video features!`",
            parse_mode="Markdown"
        )
        return
    message = " ".join(context.args)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT chat_id FROM users")
        user_ids = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        if not user_ids:
            await update.message.reply_text("❌ No users in database")
            return
        status_msg = await update.message.reply_text(f"📢 Broadcasting to {len(user_ids)} users...")
        sent = 0
        failed = 0
        for user_id in user_ids:
            try:
                await context.bot.send_message(
                    chat_id=int(user_id),
                    text=f"📢 *Announcement from Admin*\n\n{message}",
                    parse_mode="Markdown"
                )
                sent += 1
            except:
                failed += 1
        await context.bot.edit_message_text(
            chat_id=update.message.chat_id,
            message_id=status_msg.message_id,
            text=f"✅ Broadcast Complete!\n\n📨 Sent: {sent}\n❌ Failed: {failed}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("image", command_image))
    app.add_handler(CommandHandler("video", command_video))
    app.add_handler(CommandHandler("plans", command_plans))
    app.add_handler(CommandHandler("redeem", command_redeem))
    app.add_handler(CommandHandler("help", command_help))
    app.add_handler(CommandHandler("quota", command_quota))
    app.add_handler(CommandHandler("myplan", command_myplan))
    app.add_handler(CommandHandler("genkey", admin_genkey))
    app.add_handler(CommandHandler("members", admin_members))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("dbstatus", admin_dbstatus))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

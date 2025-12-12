# bot.py
import os
import json
import asyncio
import logging
import string
import random
from datetime import datetime, timedelta
import psycopg2
from nano_banana_handler import t2i_nano_handler
from psycopg2.extras import RealDictCursor

# Add under your other constants
LOG_VERBOSE = os.getenv("LOG_VERBOSE", "1") == "1"
# Sora integration
from sora_api import generate_sora_video, SoraError

# Hailuo integration (kept)
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
        if user_data.get("count", 0) >= daily_limit:
            cur.close()
            conn.close()
            return False
        cur.close()
        conn.close()
        return True
    except:
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
        pass

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

async def start(update, context):
    keyboard = [
        [InlineKeyboardButton("🖼 Text → Image (Standard)", callback_data="text2image")],
        [InlineKeyboardButton("🤖 Text → Image (Nano Banana)", callback_data="text2image_nano")],
        [InlineKeyboardButton("🎬 Text → Video (Hailuo)", callback_data="text2video_hailuo")],
        [InlineKeyboardButton("🎥 Text → Video (Sora)", callback_data="text2video_sora")],
        [InlineKeyboardButton("🎥 Image → Video", callback_data="image2video")]
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
    user_sessions[chat_id] = {"mode": "text2image", "step": "waiting_ratio"}
    await update.message.reply_text(
        "🖼 *Text to Image Mode*\n\nSelect your preferred aspect ratio:",
        parse_mode="Markdown",
        reply_markup=get_ratio_keyboard()
    )

async def command_video(update, context):
    chat_id = update.message.chat_id
    user_sessions[chat_id] = {"mode": "image2video", "step": "waiting_model"}
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
        elif session["mode"] == "text2video":
            await q.edit_message_text(
                f"✅ Aspect Ratio: *{ratio_label}*\n\n📝 Now send your *text prompt* to generate a video:",
                parse_mode="Markdown"
            )
        return
    # Handle standard text2image, nano text2image, hailuo text2video, sora text2video, and image2video
    if data in ["text2image", "image2video", "text2image_nano", "text2video_hailuo", "text2video_sora"]:
        if data == "text2image":
            user_sessions[chat_id] = {"mode": "text2image", "step": "waiting_ratio"}
            await q.edit_message_text(
                "🖼 *Text to Image Mode*\n\nSelect your preferred aspect ratio:",
                parse_mode="Markdown",
                reply_markup=get_ratio_keyboard()
            )
        elif data == "text2image_nano":
            # mark session to use Nano Banana provider
            user_sessions[chat_id] = {"mode": "text2image", "step": "waiting_ratio", "nano_banana": True}
            await q.edit_message_text(
                "🤖 *Nano Banana — Text to Image Mode*\n\nSelect your preferred aspect ratio:",
                parse_mode="Markdown",
                reply_markup=get_ratio_keyboard()
            )
        elif data == "text2video_hailuo":
            # Start Hailuo simple flow: ask for prompt immediately
            user_sessions[chat_id] = {"mode": "hailuo", "step": "waiting_prompt"}
            await q.edit_message_text(
                "🎬 *Hailuo Text → Video*\n\nSend your *text prompt* and I will generate a vertical 720x1280 video for you:",
                parse_mode="Markdown"
            )
        elif data == "text2video_sora":
            # Start Sora simple flow: ask for prompt immediately
            user_sessions[chat_id] = {"mode": "sora", "step": "waiting_prompt"}
            await q.edit_message_text(
                "🎬 *Sora Text → Video*\n\nSend your *text prompt* and I will generate a video for you (default 1280x720):",
                parse_mode="Markdown"
            )
        elif data == "image2video":
            user_sessions[chat_id] = {"mode": "image2video", "step": "waiting_model"}
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

    # --- Sora simple flow: waiting_prompt ---
    if session.get("mode") == "sora" and session.get("step") == "waiting_prompt":
        if not check_limit(chat_id):
            daily_limit = get_user_daily_limit(chat_id)
            await update.message.reply_text(
                f"❌ Daily Limit Reached\n"
                f"You've used all {daily_limit} generations today.\n\n"
                f"Use `/redeem KEY` to get more generations",
                parse_mode="Markdown"
            )
            return
        status_msg = await update.message.reply_text("⏳ Generating Sora video (1280x720)... This can take a while.")
        try:
            loop = asyncio.get_event_loop()
            # default Sora size set to 1280x720 (16:9)
            result = await loop.run_in_executor(None, generate_sora_video, text, 4, "1280x720")
            if isinstance(result, tuple):
                video_bytes, final_url = result
            else:
                video_bytes = result
                final_url = None

            if not video_bytes:
                raise ValueError("No video bytes received from Sora")

            import io, os as _os, tempfile
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            try:
                tf.write(video_bytes)
                tf.flush()
                tf.close()
                filesize = _os.path.getsize(tf.name)
                try:
                    if filesize <= 50 * 1024 * 1024:  # 50 MB threshold
                        await update.message.reply_video(open(tf.name, "rb"), caption="🎬 Generated by Sora")
                    else:
                        await update.message.reply_document(open(tf.name, "rb"), caption="🎬 Generated by Sora (document)")
                except Exception as send_err:
                    try:
                        if final_url:
                            await update.message.reply_text(f"✅ Video ready but sending failed. Download here: {final_url}")
                        else:
                            await update.message.reply_text(f"✅ Video ready but sending failed. Error: {send_err}")
                    except:
                        pass
                increment_usage(chat_id)
            finally:
                try:
                    _os.unlink(tf.name)
                except:
                    pass

            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except:
                pass
            return
        except SoraError as se:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except:
                pass
            await update.message.reply_text(f"❌ Sora error: {se}")
            return
        except Exception as e:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except:
                pass
            await update.message.reply_text(f"❌ Unexpected Sora error: {e}")
            return

    # --- Hailuo simple flow: waiting_prompt (unchanged) ---
    if session.get("mode") == "hailuo" and session.get("step") == "waiting_prompt":
        if not check_limit(chat_id):
            daily_limit = get_user_daily_limit(chat_id)
            await update.message.reply_text(
                f"❌ Daily Limit Reached\n"
                f"You've used all {daily_limit} generations today.\n\n"
                f"Use `/redeem KEY` to get more generations",
                parse_mode="Markdown"
            )
            return
        status_msg = await update.message.reply_text("⏳ Generating Hailuo video (720x1280)... This can take a while.")
        try:
            loop = asyncio.get_event_loop()
            video_result = await loop.run_in_executor(None, generate_hailuo_video, text, 6, "720x1280")
            video_bytes = None
            final_url = None
            if isinstance(video_result, tuple):
                video_bytes, final_url = video_result
            else:
                video_bytes = video_result

            if not video_bytes:
                raise ValueError("No video bytes received from Hailuo")

            import io, os as _os, tempfile
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            try:
                tf.write(video_bytes)
                tf.flush()
                tf.close()
                filesize = _os.path.getsize(tf.name)
                try:
                    if filesize <= 50 * 1024 * 1024:
                        await update.message.reply_video(open(tf.name, "rb"), caption="🎬 Generated by Hailuo")
                    else:
                        await update.message.reply_document(open(tf.name, "rb"), caption="🎬 Generated by Hailuo (document)")
                except Exception as send_err:
                    try:
                        if final_url:
                            await update.message.reply_text(f"✅ Video ready but sending failed. Download here: {final_url}")
                        else:
                            await update.message.reply_text(f"✅ Video ready but sending failed. Error: {send_err}")
                    except:
                        pass
                increment_usage(chat_id)
            finally:
                try:
                    _os.unlink(tf.name)
                except:
                    pass

            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except:
                pass
            return
        except HailuoError as he:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except:
                pass
            await update.message.reply_text(f"❌ Hailuo error: {he}")
            return
        except Exception as e:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except:
                pass
            await update.message.reply_text(f"❌ Unexpected Hailuo error: {e}")
            return

    # fallback: previous logic for other flows (unchanged)
    if session.get("step") == "waiting_ratio":
        await update.message.reply_text(
            "⚠️ Please select an aspect ratio first:",
            reply_markup=get_ratio_keyboard()
        )
        return
    if not check_limit(chat_id):
        daily_limit = get_user_daily_limit(chat_id)
        await update.message.reply_text(
            f"❌ Daily Limit Reached\n"
            f"You've used all {daily_limit} generations today.\n\n"
            f"Use `/redeem KEY` to get more generations",
            parse_mode="Markdown"
        )
        return
    try:
        user_name = update.message.from_user.first_name
        ratio = session.get("aspect_ratio", "1:1")
        await context.bot.send_message(
            chat_id=ADMIN_ID, 
            text=f"🕵️ *Log*\n👤 {user_name} (`{chat_id}`)\n🎯 {session['mode']}\n📐 Ratio: {ratio}\n📝 {text}",
            parse_mode="Markdown"
        )
    except: pass
    hf = HiggsfieldAPI(os.getenv("HF_KEY"), os.getenv("HF_SECRET"))
    payload = {}
    model_id = ""
    status_msg = await update.message.reply_text("⏳ Initializing...")
    aspect_ratio = session.get("aspect_ratio", "1:1")

    # --- Nano Banana branch (unchanged) ---
    if session["mode"] == "text2image" and session.get("nano_banana"):
        try:
            await update.message.reply_text("⏳ Generating image with Nano Banana…")
            loop = asyncio.get_event_loop()
            from nano_banana_api import generate_nano_image, NanoBananaError

            size_map = {"9:16": "1024x2048", "16:9": "2048x1024", "1:1": "1024x1024"}
            size = size_map.get(aspect_ratio, "1024x1024")

            image_bytes = await loop.run_in_executor(None, generate_nano_image, text, size)

            import io
            bio = io.BytesIO(image_bytes)
            bio.name = "nano.png"
            bio.seek(0)

            increment_usage(chat_id)

            await update.message.reply_document(document=bio)

            user_mention = update.message.from_user.first_name or "Unknown"
            ratio_label = {"9:16": "📱 9:16", "16:9": "💻 16:9", "1:1": "⬜ 1:1"}.get(aspect_ratio, aspect_ratio)
            log_text = (
                f"🧾 *Log*\n"
                f"👤 {user_mention} (`{chat_id}`)\n"
                f"🎯 text2image\n"
                f"📐 Ratio: {ratio_label}\n\n"
                f"📝 {text[:800]}"
            )
            await update.message.reply_text(log_text, parse_mode="Markdown")

            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except:
                pass

            return
        except Exception as e:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
            except:
                pass
            await update.message.reply_text(f"❌ Nano Banana error: {e}")
            return

    # --- Existing HuggingFace / Higgsfield flow (unchanged) ---
    if session["mode"] == "text2image":
        model_id = "higgsfield-ai/soul/standard"
        payload = {"prompt": text, "aspect_ratio": aspect_ratio}
    elif session["mode"] == "image2video":
        if session.get("step") != "waiting_prompt":
            await update.message.reply_text("Send an image first!")
            return
        model_id = session.get("video_model", "higgsfield-ai/dop/turbo")
        payload = {"prompt": text, "image_url": session["image_url"], "aspect_ratio": aspect_ratio}
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
            elif "video" in final:
                v = final["video"]
                media_url = v.get("url") if isinstance(v, dict) else (v[0].get("url") if isinstance(v, list) else v)
            elif "output_url" in final: media_url = final["output_url"]
            elif "result" in final: media_url = final["result"]
            if not media_url: raise ValueError(f"No URL found: {final.keys()}")
            ratio_label = {"9:16": "📱 9:16", "16:9": "💻 16:9", "1:1": "⬜ 1:1"}.get(aspect_ratio, aspect_ratio)
            caption_text = f"✨ Here is your result!\n📐 Ratio: {ratio_label}\n\n🔔 Subscribe: @HiggsMasterBotChannel"
            if session["mode"] == "image2video":
                await update.message.reply_video(media_url, caption=caption_text)
            else:
                await update.message.reply_photo(media_url, caption=caption_text)
            await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        else:
            await update.message.reply_text(f"❌ Failed: {final.get('status')}")
    except Exception as e:
        stop_event.set()
        await update.message.reply_text(f"❌ Error: {e}")

async def command_help(update, context):
    help_text = (
        "📚 *Available Commands*\n\n"
        "*Generation:*\n"
        "/image - Generate image from text\n"
        "/video - Animate photo with motion\n\n"
        "*Quota & Plans:*\n"
        "/quota - Check remaining generations today\n"
        "/myplan - View your current plan\n"
        "/plans - View all pricing plans\n\n"
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
    # nano direct command (keeps existing flows intact)
    app.add_handler(CommandHandler("nano", t2i_nano_handler))
    # hailuo direct command (if you have hailuo_handler)
    app.add_handler(CommandHandler("hailuo", t2v_hailuo_handler))
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

# EOF

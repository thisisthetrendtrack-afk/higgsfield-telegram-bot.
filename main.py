import os
import time
from telegram.ext import ApplicationBuilder
from telegram.error import Conflict
from telegram import BotCommand

from bot import register_handlers, init_db, migrate_from_json


async def setup_commands(app):
    """Register all bot commands with Telegram"""
    await app.bot.set_my_commands([
        BotCommand("start", "Main menu"),
        BotCommand("image", "Generate image from text"),
        BotCommand("video", "Animate photo with motion"),
        BotCommand("quota", "Check remaining generations"),
        BotCommand("myplan", "View your current plan"),
        BotCommand("plans", "View all pricing plans"),
        BotCommand("redeem", "Redeem a premium plan key"),
        BotCommand("help", "Show all commands"),
        BotCommand("genkey", "🔐 Admin: Generate redemption keys"),
        BotCommand("members", "🔐 Admin: View premium members"),
        BotCommand("broadcast", "🔐 Admin: Send announcement to all users"),
    ])
    print("✅ Commands registered with Telegram")


def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    HF_KEY = os.getenv("HF_KEY")
    HF_SECRET = os.getenv("HF_SECRET")
    DATABASE_URL = os.getenv("DATABASE_URL")

    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN missing in environment variables")

    if not DATABASE_URL:
        raise RuntimeError("❌ DATABASE_URL missing in environment variables")

    # HF keys are only required if Higgsfield is enabled
    if not HF_KEY or not HF_SECRET:
        print("⚠️ HF_KEY / HF_SECRET missing — Higgsfield models disabled")

    print("🚀 Higgsfield Bot Starting...")

    # Initialize database & migrate old JSON data
    init_db()
    migrate_from_json()

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register handlers from bot.py
    register_handlers(app)

    # Register commands after bot starts
    app.post_init = setup_commands

    max_retries = 5
    retry_count = 0

    while retry_count < max_retries:
        try:
            app.run_polling(allowed_updates=[])
            break
        except Conflict:
            retry_count += 1
            wait_time = 10 + (retry_count * 5)
            print(
                f"⚠️ Telegram conflict detected "
                f"(retry {retry_count}/{max_retries}). Waiting {wait_time}s..."
            )
            time.sleep(wait_time)
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            raise


if __name__ == "__main__":
    main()

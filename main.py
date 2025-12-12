import os
import time
from telegram.ext import ApplicationBuilder
from telegram.error import Conflict
from telegram import BotCommand

from bot import register_handlers, init_db, migrate_from_json


async def setup_commands(app):
    """Register bot commands with Telegram"""
    await app.bot.set_my_commands([
        BotCommand("start", "Main menu"),
        BotCommand("image", "Generate image from text"),
        BotCommand("video", "Generate video"),
        BotCommand("quota", "Check remaining generations"),
        BotCommand("myplan", "View your current plan"),
        BotCommand("plans", "View pricing plans"),
        BotCommand("redeem", "Redeem a premium plan key"),
        BotCommand("help", "Show help"),
        BotCommand("genkey", "Admin: Generate keys"),
        BotCommand("members", "Admin: View members"),
        BotCommand("broadcast", "Admin: Broadcast message"),
    ])
    print("✅ Commands registered")


def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL")

    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN is missing")

    if not DATABASE_URL:
        raise RuntimeError("❌ DATABASE_URL is missing")

    print("🚀 Bot starting...")

    # Initialize DB and migrate old JSON data
    init_db()
    migrate_from_json()

    # Build Telegram application
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register all handlers from bot.py
    register_handlers(app)

    # Register commands after startup
    app.post_init = setup_commands

    # Safe polling with retry (Railway-friendly)
    retries = 0
    while retries < 5:
        try:
            app.run_polling(allowed_updates=[])
            break
        except Conflict:
            retries += 1
            wait = 10 + retries * 5
            print(f"⚠️ Conflict detected, retry {retries}/5 — waiting {wait}s")
            time.sleep(wait)
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            raise


if __name__ == "__main__":
    main()

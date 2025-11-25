import os
import time
from telegram.ext import ApplicationBuilder
from telegram.error import Conflict
from bot import register_handlers


def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    HF_KEY = os.getenv("HF_KEY")
    HF_SECRET = os.getenv("HF_SECRET")

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing in environment variables")

    if not HF_KEY or not HF_SECRET:
        raise RuntimeError("HF_KEY or HF_SECRET missing in environment variables")

    print("🚀 Higgsfield Bot Starting...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    register_handlers(app)

    # Run with retry logic for 409 Conflict errors
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            app.run_polling(allowed_updates=[])
            break
        except Conflict as e:
            retry_count += 1
            wait_time = 10 + (retry_count * 5)  # 15, 20, 25, 30, 35 seconds
            print(f"⚠️ Conflict detected (retry {retry_count}/{max_retries}). Waiting {wait_time}s...")
            time.sleep(wait_time)
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            raise


if __name__ == "__main__":
    main()

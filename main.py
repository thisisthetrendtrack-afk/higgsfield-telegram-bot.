import os
from bot import run_bot

# Simple entrypoint for Railway
# Railway starts the container → Python runs main.py → bot starts

if __name__ == "__main__":
    # Ensure required variables exist
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    HF_KEY = os.getenv("HF_KEY")
    HF_SECRET = os.getenv("HF_SECRET")

    if not TELEGRAM_TOKEN:
        raise RuntimeError("Error: TELEGRAM_TOKEN missing in Railway variables")

    if not HF_KEY or not HF_SECRET:
        raise RuntimeError("Error: HF_KEY or HF_SECRET missing in Railway variables")

    print("Starting Telegram bot...")
    run_bot()

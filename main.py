import os
from telegram.ext import ApplicationBuilder
from bot import start_handler, button_handler, message_handler


def main():
    BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
    HF_KEY = os.getenv("HF_KEY")
    HF_SECRET = os.getenv("HF_SECRET")

    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN missing in Railway Variables")
    if not HF_KEY or not HF_SECRET:
        raise RuntimeError("HF_KEY or HF_SECRET missing in Railway Variables")

    print("Starting HiggsMasterBot...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # add handlers
    app.add_handler(start_handler)
    app.add_handler(button_handler)
    app.add_handler(message_handler)

    print("Bot is now running…")
    app.run_polling()


if __name__ == "__main__":
    main()

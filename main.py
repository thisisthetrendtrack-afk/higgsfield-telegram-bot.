import os
from telegram.ext import ApplicationBuilder
from bot import register_handlers


def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    HF_KEY = os.getenv("HF_KEY")
    HF_SECRET = os.getenv("HF_SECRET")

    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing in Railway Variables")

    if not HF_KEY or not HF_SECRET:
        raise RuntimeError("HF_KEY or HF_SECRET missing in Railway Variables")

    print("🚀 Higgsfield Bot Starting...")

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    register_handlers(app)

    app.run_polling()


if __name__ == "__main__":
    main()

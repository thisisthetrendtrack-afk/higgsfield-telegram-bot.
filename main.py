import os
import asyncio
from telegram.ext import ApplicationBuilder
from dotenv import load_dotenv

from bot import (
    start_handler,
    help_handler,
    image2video_handler,
    prompt_handler,
    status_handler,
)
from higgsfield_api import HiggsfieldAPI
from utils import setup_logging


async def main():
    setup_logging()
    load_dotenv()

    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    HF_KEY = os.getenv("HF_KEY")
    HF_SECRET = os.getenv("HF_SECRET")

    if not TELEGRAM_TOKEN:
        raise RuntimeError("Error: TELEGRAM_TOKEN not found in Railway Variables")

    if not HF_KEY or not HF_SECRET:
        raise RuntimeError("Error: HF_KEY or HF_SECRET missing in Railway Variables")

    hf_api = HiggsfieldAPI(HF_KEY, HF_SECRET)

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(lambda app: app.bot_data.update({"hf_api": hf_api}))
        .build()
    )

    # Register Handlers
    application.add_handler(start_handler)
    application.add_handler(help_handler)
    application.add_handler(image2video_handler)
    application.add_handler(status_handler)
    application.add_handler(prompt_handler)

    print("Bot is running...")

    # 🚀 FIXED — remove ALL arguments:
    await application.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
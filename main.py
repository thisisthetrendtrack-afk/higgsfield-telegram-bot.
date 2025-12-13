# main.py
import os
from telegram.ext import ApplicationBuilder

from bot import (
    register_handlers,
    init_db,
    migrate_from_json
)

def main():
    init_db()
    migrate_from_json()

    app = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()
    register_handlers(app)

    print("🤖 Bot started successfully")
    app.run_polling()

if __name__ == "__main__":
    main()

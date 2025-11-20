"""
Async entrypoint for the Telegram bot.

This module is responsible for bootstrapping the Telegram application,
loading environment variables, configuring the Higgsfield API wrapper and
registering all handlers defined in the ``bot`` module. When executed
directly it will start the polling loop to listen for incoming
messages from Telegram users.
"""

from __future__ import annotations

import asyncio
import os
import logging

from dotenv import load_dotenv
from telegram import BotCommand
from telegram.ext import Application, ApplicationBuilder

from bot import register_handlers
from higgsfield_api import HiggsfieldAPI
from utils import setup_logging


async def main() -> None:
    """Main asynchronous entry point.

    This function performs the following operations:

    * Loads environment variables from a local ``.env`` file when present.
    * Configures Python logging for more readable output.
    * Constructs the ``HiggsfieldAPI`` wrapper using the supplied secret
      credentials.
    * Builds the Telegram ``Application`` and stores the API wrapper on
      ``bot_data`` so that handlers can access it.
    * Registers all command and message handlers.
    * Defines the bot's command list so that Telegram clients can show
      a command menu.
    * Starts the polling loop and blocks until the process is shut down.

    Raises:
        RuntimeError: If the ``TELEGRAM_TOKEN`` environment variable is
            missing. Without this token the bot cannot authenticate with
            Telegram's servers.
    """
    # Load environment variables from .env for local development. Railway will
    # inject environment variables automatically when deploying.
    load_dotenv()

    # Configure logging with sensible defaults.
    setup_logging()

    token = os.getenv("TELEGRAM_TOKEN")
    hf_key = os.getenv("HF_KEY")
    hf_secret = os.getenv("HF_SECRET")

    if not token:
        raise RuntimeError(
            "The TELEGRAM_TOKEN environment variable is not set. "
            "Please provide your bot token via the Railway dashboard or a .env file."
        )

    # Instantiate the API wrapper. If ``hf_key`` and ``hf_secret`` are ``None``
    # the wrapper will still function, but authenticated endpoints will fail.
    api_wrapper = HiggsfieldAPI(hf_key, hf_secret)

    # Build the Telegram application. Using ``ApplicationBuilder`` ensures
    # compatibility with python‑telegram‑bot v20+ which relies on asyncio.
    application: Application = ApplicationBuilder().token(token).build()

    # Store the API wrapper on bot_data so handlers have easy access.
    application.bot_data["api"] = api_wrapper

    # Register all handlers defined in the bot module.
    register_handlers(application)

    # Define the list of available commands. This will cause Telegram clients
    # to show a command menu when the user types '/' in a chat with the bot.
    commands = [
        BotCommand("start", "Start the bot and display a welcome message"),
        BotCommand("help", "Display help information"),
        BotCommand("image2video", "Generate a video from an uploaded image"),
        BotCommand("speak", "Placeholder command – not yet implemented"),
        BotCommand("soul", "Placeholder command – not yet implemented"),
        BotCommand("motions", "Placeholder command – not yet implemented"),
        BotCommand("characters", "Placeholder command – not yet implemented"),
        BotCommand("status", "Check the status of an existing job"),
        BotCommand("delete_character", "Placeholder command – not yet implemented"),
    ]

    # The bot must be initialized before commands can be set. ``initialize``
    # implicitly occurs during ``run_polling``, so we call it here explicitly
    # to ensure ``set_my_commands`` is available.
    await application.initialize()
    await application.bot.set_my_commands(commands)

    # Start polling. ``run_polling`` will initialise the application if it
    # hasn't been initialised yet, start receiving updates and block until
    # a signal (Ctrl+C) is received or the task is cancelled. Because we've
    # already called ``initialize`` above we can pass ``initialize=False``.
    await application.run_polling(
        stop_signals=None,  # rely on default termination signals
        close_loop=False,
        initialize=False,
    )


if __name__ == "__main__":
    asyncio.run(main())
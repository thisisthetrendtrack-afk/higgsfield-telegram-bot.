# nano_banana_handler.py
import io
import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from nano_banana_api import generate_nano_image, NanoBananaError

logger = logging.getLogger(__name__)

async def t2i_nano_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nano <prompt>  or reply to message with /nano
    """
    # extract prompt text
    prompt = None
    if context.args:
        prompt = " ".join(context.args).strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        prompt = update.message.reply_to_message.text.strip()

    if not prompt:
        await update.message.reply_text("Usage: /nano <prompt>\nOr reply to a message containing the prompt with /nano")
        return

    # Inform user we started generation
    status_msg = await update.message.reply_text("Generating image (Nano Banana)…")

    try:
        # run blocking HTTP call in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        image_bytes = await loop.run_in_executor(None, generate_nano_image, prompt)

        bio = io.BytesIO(image_bytes)
        bio.name = "nano.png"
        bio.seek(0)

        # send as photo (Telegram will compress) — change to reply_document if you want full quality
        await update.message.reply_photo(photo=bio, caption=f"Generated for: {prompt[:200]}")
    except NanoBananaError as e:
        logger.exception("Nano Banana error")
        await update.message.reply_text(f"Image generation failed: {e}")
    except Exception as e:
        logger.exception("Unexpected error in t2i_nano_handler")
        await update.message.reply_text("Unexpected error while generating image.")
    finally:
        try:
            await status_msg.delete()
        except Exception:
            pass

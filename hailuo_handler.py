# hailuo_handler.py
import io
import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes
from hailuo_api import generate_hailuo_video, HailuoError

logger = logging.getLogger(__name__)

async def t2v_hailuo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /hailuo <prompt>  — generate a short video from text via ModelsLab Hailuo.
    """
    prompt = None
    if context.args:
        prompt = " ".join(context.args).strip()
    elif update.message.reply_to_message and update.message.reply_to_message.text:
        prompt = update.message.reply_to_message.text.strip()

    if not prompt:
        await update.message.reply_text("Usage: /hailuo <prompt>\nOr reply to a message with /hailuo")
        return

    status_msg = await update.message.reply_text("Generating video with Hailuo… this may take a while.")
    try:
        loop = asyncio.get_event_loop()
        # default duration and size are configurable
        duration = 6
        size = "720x1280"
        video_bytes = await loop.run_in_executor(None, generate_hailuo_video, prompt, duration, size)

        bio = io.BytesIO(video_bytes)
        bio.name = "hailuo.mp4"
        bio.seek(0)

        # send as video (telegram will accept bytes)
        await update.message.reply_video(video=bio, caption=f"Generated with Hailuo:\n{prompt[:200]}")
    except HailuoError as e:
        logger.exception("HailuoError")
        await update.message.reply_text(f"❌ Hailuo error: {e}")
    except Exception as e:
        logger.exception("Unexpected hailuo error")
        await update.message.reply_text("❌ Unexpected error while generating video.")
    finally:
        try:
            await status_msg.delete()
        except:
            pass

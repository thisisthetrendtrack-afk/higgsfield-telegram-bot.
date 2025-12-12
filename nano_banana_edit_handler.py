# nano_banana_edit_handler.py
import asyncio
import io
import tempfile
import os
from telegram import Update
from telegram.ext import ContextTypes
from nano_banana_edit_api import generate_nano_edit_image, NanoBananaEditError

# NOTE: this module expects your bot's global `user_sessions` dict to exist and be shared.
# In bot.py we will import the two handler functions and register them.

async def t2i_nano_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nano_edit command or menu callback entry point.
    Sets session to expect a photo first.
    """
    chat_id = update.effective_chat.id
    # create or overwrite session
    context.application.user_data.setdefault(chat_id, {})
    # we rely on bot.py's user_sessions global; if not available, use application.user_data fallback
    try:
        # prefer global user_sessions if exists
        user_sessions = context.application.bot_data.get("user_sessions")
        if user_sessions is not None:
            user_sessions[chat_id] = {"mode": "nano_edit", "step": "waiting_photo"}
        else:
            context.application.user_data[chat_id] = {"mode": "nano_edit", "step": "waiting_photo"}
    except:
        # fallback
        context.application.user_data[chat_id] = {"mode": "nano_edit", "step": "waiting_photo"}

    await update.message.reply_text("🛠 *Nano Banana Pro — Image Edit*\n\nSend the *photo* you want to edit (then you'll be asked for the prompt).", parse_mode="Markdown")

async def nano_edit_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles incoming PHOTO when session indicates nano_edit and asks for prompt next.
    Register this handler *before* your global photo handler so it takes precedence.
    """
    chat_id = update.effective_chat.id
    # get session from global user_sessions if bot stores it there
    user_sessions = context.application.bot_data.get("user_sessions")
    session = None
    if user_sessions is not None:
        session = user_sessions.get(chat_id)
    else:
        session = context.application.user_data.get(chat_id)

    if not session or session.get("mode") != "nano_edit" or session.get("step") != "waiting_photo":
        return  # not our conversation

    # Save photo file_url or bytes in session then ask for prompt
    try:
        photo_obj = await update.message.photo[-1].get_file()
        file_path = photo_obj.file_path
        # Try to fetch bytes from Telegram file path (works when path starts with http)
        # Use get_file().download_as_bytearray() for robust bytes fetching
        b = await photo_obj.download_as_bytearray()
        # store bytes
        if user_sessions is not None:
            user_sessions[chat_id]["image_bytes"] = bytes(b)
        else:
            context.application.user_data[chat_id]["image_bytes"] = bytes(b)
        if user_sessions is not None:
            user_sessions[chat_id]["step"] = "waiting_prompt"
        else:
            context.application.user_data[chat_id]["step"] = "waiting_prompt"

        await update.message.reply_text("✅ Photo received. Now send the *prompt* describing the edit you want (e.g. 'make it cinematic, teal-orange grade, add fog').", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error receiving photo: {e}")

async def nano_edit_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles TEXT when session indicates nano_edit and step == waiting_prompt.
    Calls generate_nano_edit_image and returns edited image.
    Register this handler before your global text handler.
    """
    chat_id = update.effective_chat.id
    text = update.message.text
    user_sessions = context.application.bot_data.get("user_sessions")
    session = None
    if user_sessions is not None:
        session = user_sessions.get(chat_id)
    else:
        session = context.application.user_data.get(chat_id)

    if not session or session.get("mode") != "nano_edit" or session.get("step") != "waiting_prompt":
        return  # not our conversation

    # get image bytes
    image_bytes = session.get("image_bytes") if session else context.application.user_data.get(chat_id, {}).get("image_bytes")
    if not image_bytes:
        await update.message.reply_text("⚠️ No photo found. Please send the photo first.")
        # reset session to waiting_photo
        if user_sessions is not None:
            user_sessions[chat_id] = {"mode": "nano_edit", "step": "waiting_photo"}
        else:
            context.application.user_data[chat_id] = {"mode": "nano_edit", "step": "waiting_photo"}
        return

    status_msg = await update.message.reply_text("⏳ Editing image with Nano Banana Pro...")
    try:
        loop = asyncio.get_event_loop()
        # call blocking API in executor
        # generate_nano_edit_image returns (bytes, url) in our API module
        result = await loop.run_in_executor(None, generate_nano_edit_image, image_bytes, text, None, None)
        image_out = None
        final_url = None
        if isinstance(result, tuple):
            image_out, final_url = result
        else:
            image_out = result

        if not image_out:
            raise NanoBananaEditError("No image bytes returned")

        bio = io.BytesIO(image_out)
        bio.name = "nano_edit.png"
        bio.seek(0)

        # Send edited image
        await update.message.reply_document(document=bio, caption="Edited with Nano Banana Pro")

        # cleanup session
        if user_sessions is not None:
            user_sessions.pop(chat_id, None)
        else:
            context.application.user_data.pop(chat_id, None)

        # delete status msg
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        except:
            pass

    except NanoBananaEditError as ne:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        except:
            pass
        await update.message.reply_text(f"❌ Nano Banana Edit error: {ne}")
    except Exception as e:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=status_msg.message_id)
        except:
            pass
        await update.message.reply_text(f"❌ Unexpected error: {e}")

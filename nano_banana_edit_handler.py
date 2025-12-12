# nano_banana_edit_handler.py
import asyncio
import io
import tempfile
import os
from telegram import Update
from telegram.ext import ContextTypes
from nano_banana_edit_api import generate_nano_edit_image, NanoBananaEditError

# This handler expects the bot to expose the shared `user_sessions` dict via
# application.bot_data["user_sessions"] OR to use module-level storage fallback.

async def t2i_nano_edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /nano_edit command or menu entry.
    """
    chat_id = update.effective_chat.id
    # prefer application.bot_data shared sessions if present
    app_sessions = context.application.bot_data.get("user_sessions")
    if app_sessions is not None:
        app_sessions[chat_id] = {"mode": "nano_edit", "step": "waiting_photo"}
    else:
        # fallback: put into application.user_data keyed by chat_id
        context.application.user_data[chat_id] = {"mode": "nano_edit", "step": "waiting_photo"}
    await update.message.reply_text(
        "🛠 *Nano Banana Pro — Image Edit*\n\nSend the *photo* you want to edit (then you'll be asked for the prompt).",
        parse_mode="Markdown"
    )

async def nano_edit_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles incoming PHOTO when session indicates nano_edit and asks for prompt next.
    Stores a public Telegram file URL as init_image_url in session (do NOT store bytes).
    """
    chat_id = update.effective_chat.id
    app_sessions = context.application.bot_data.get("user_sessions")
    session = None
    if app_sessions is not None:
        session = app_sessions.get(chat_id)
    else:
        session = context.application.user_data.get(chat_id)

    if not session or session.get("mode") != "nano_edit" or session.get("step") != "waiting_photo":
        return  # not our conversation

    try:
        # get file object and file_path
        photo_obj = await update.message.photo[-1].get_file()
        file_path = photo_obj.file_path  # may be HTTP or path
        # build Telegram file URL if needed
        if file_path.startswith("http"):
            init_image_url = file_path
        else:
            init_image_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file_path}"

        # Save init_image_url in session (not raw bytes)
        if app_sessions is not None:
            app_sessions[chat_id]["init_image_url"] = init_image_url
            app_sessions[chat_id]["step"] = "waiting_prompt"
        else:
            context.application.user_data[chat_id] = context.application.user_data.get(chat_id, {})
            context.application.user_data[chat_id]["init_image_url"] = init_image_url
            context.application.user_data[chat_id]["mode"] = "nano_edit"
            context.application.user_data[chat_id]["step"] = "waiting_prompt"

        await update.message.reply_text("✅ Photo received. Now send the *prompt* describing the edit you want.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error receiving photo: {e}")

async def nano_edit_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles TEXT when session indicates nano_edit and step == waiting_prompt.
    Calls generate_nano_edit_image with init_image_url string.
    """
    chat_id = update.effective_chat.id
    text = update.message.text
    app_sessions = context.application.bot_data.get("user_sessions")
    session = None
    if app_sessions is not None:
        session = app_sessions.get(chat_id)
    else:
        session = context.application.user_data.get(chat_id)

    if not session or session.get("mode") != "nano_edit" or session.get("step") != "waiting_prompt":
        return  # not our conversation

    init_image_url = session.get("init_image_url") if session else context.application.user_data.get(chat_id, {}).get("init_image_url")
    if not init_image_url:
        # reset to waiting_photo
        if app_sessions is not None:
            app_sessions[chat_id] = {"mode": "nano_edit", "step": "waiting_photo"}
        else:
            context.application.user_data[chat_id] = {"mode": "nano_edit", "step": "waiting_photo"}
        await update.message.reply_text("⚠️ No photo URL found. Please send the photo first.")
        return

    status_msg = await update.message.reply_text("⏳ Editing image with Nano Banana Pro...")
    try:
        loop = asyncio.get_event_loop()
        # Call blocking API in executor with init_image_url (string)
        result = await loop.run_in_executor(None, generate_nano_edit_image, init_image_url, text, None, None)
        edited_bytes = None
        final_url = None
        if isinstance(result, tuple):
            edited_bytes, final_url = result
        else:
            edited_bytes = result

        if not edited_bytes:
            raise NanoBananaEditError("No image bytes returned from Nano Banana Edit API")

        import io, os as _os, tempfile
        bio = io.BytesIO(edited_bytes)
        bio.name = "nano_edit.png"
        bio.seek(0)

        await update.message.reply_document(document=bio, caption="Edited with Nano Banana Pro")

        # cleanup session
        if app_sessions is not None:
            app_sessions.pop(chat_id, None)
        else:
            context.application.user_data.pop(chat_id, None)

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

# nano_edit_photo_handler replacement (copy-paste into your handler module / bot.py)
async def nano_edit_photo_handler(update, context):
    chat_id = update.effective_chat.id
    app_sessions = context.application.bot_data.get("user_sessions")
    session = app_sessions.get(chat_id) if app_sessions is not None else user_sessions.get(chat_id)
    # Only handle when in nano_edit waiting_photo
    if not session or session.get("mode") != "nano_edit" or session.get("step") != "waiting_photo":
        return

    try:
        file_obj = await update.message.photo[-1].get_file()
        file_path = file_obj.file_path  # might be http or relative path
        if file_path.startswith("http"):
            init_image_url = file_path
        else:
            # build public Telegram file URL
            init_image_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file_path}"

        # store URL in session (do NOT store bytes)
        if app_sessions is not None:
            app_sessions[chat_id]["init_image_url"] = init_image_url
            app_sessions[chat_id]["step"] = "waiting_prompt"
        else:
            user_sessions[chat_id] = user_sessions.get(chat_id, {})
            user_sessions[chat_id]["init_image_url"] = init_image_url
            user_sessions[chat_id]["mode"] = "nano_edit"
            user_sessions[chat_id]["step"] = "waiting_prompt"

        await update.message.reply_text("✅ Photo received. Now send the *prompt* describing the edit you want.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error receiving photo: {e}")

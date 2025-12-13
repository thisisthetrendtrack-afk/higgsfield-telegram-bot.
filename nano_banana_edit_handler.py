# nano_banana_edit_handler.py
# This file is imported by bot.py
async def nano_edit_photo_handler(update, context):
    chat_id = update.message.chat_id
    # Assuming user_sessions is available in the scope where this is imported/used
    # If not, you might need to pass it or use context.application.bot_data
    session = context.application.bot_data.get("user_sessions", {}).get(chat_id) or user_sessions.get(chat_id)
    
    # Initialize list for image URLs if not present
    if session and "init_image_urls" not in session:
        session["init_image_urls"] = []
        
    # Only handle when in nano_edit waiting_photo or waiting_photo_2
    if not session or session.get("mode") != "nano_edit" or session.get("step") not in ("waiting_photo", "waiting_photo_2"):
        return

    try:
        file_obj = await update.message.photo[-1].get_file()
        file_path = file_obj.file_path  # might be http or relative path
        if file_path.startswith("http"):
            image_url = file_path
        else:
            # build public Telegram file URL
            image_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file_path}"

        # store URL in session (do NOT store bytes)
        session["init_image_urls"].append(image_url)
        
        if len(session["init_image_urls"]) == 1:
            session["step"] = "waiting_photo_2"
            await update.message.reply_text("✅ Photo 1 received. Now send *Photo 2*.", parse_mode="Markdown")
        elif len(session["init_image_urls"]) == 2:
            session["step"] = "waiting_prompt"
            await update.message.reply_text("✅ Photo 2 received. Now send the *prompt* describing the edit you want.", parse_mode="Markdown")
        else:
            # Should not happen, but clear if it does
            session["init_image_urls"] = [image_url]
            session["step"] = "waiting_photo_2"
            await update.message.reply_text("⚠️ Too many photos received. Starting over. Send *Photo 2*.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Error receiving photo: {e}")

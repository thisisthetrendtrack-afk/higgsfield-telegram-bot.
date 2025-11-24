# -----------------------------
# PHOTO HANDLER (Updated)
# -----------------------------
async def photo_handler(update, context):
    try:
        chat_id = update.message.chat_id
        session = user_sessions.get(chat_id)

        # 1. Check if user is in the right mode
        if not session or session.get("mode") != "image2video":
            await update.message.reply_text("⚠ Please run /start and select '🎥 Image → Video' first.")
            return

        # 2. Send a temporary status message
        status_msg = await update.message.reply_text("📥 Processing image...")

        # 3. Get the file (Robust Method)
        photo_file = await update.message.photo[-1].get_file()
        
        # Use .link if available, otherwise construct it manually
        if hasattr(photo_file, 'link') and photo_file.link:
            image_url = photo_file.link
        else:
            # Fallback for older versions or edge cases
            image_url = photo_file.file_path

        # 4. Save to session
        session["image_url"] = image_url
        session["step"] = "waiting_prompt"
        
        # 5. Success Message
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg.message_id,
            text="✅ **Image linked!**\n\nNow send a **text prompt** to animate it (e.g., 'Zoom in', 'The character blinks').",
            parse_mode="Markdown"
        )
        print(f"📸 Image processed for {chat_id}: {image_url}")

    except Exception as e:
        print(f"❌ Error in photo_handler: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def txt2img(update, context):
    chat_id = update.message.chat_id
    prompt = update.message.text

    await update.message.reply_text("Processing txt2img...")

    try:
        job_set_id, raw = await context.bot_data["hf_api"].txt2img(prompt)

        if not job_set_id:
            await update.message.reply_text("API error: No job_set_id returned.")
            return

        # Poll job status
        for _ in range(45):
            status_json = await context.bot_data["hf_api"].get_job_status(job_set_id)
            status = status_json.get("status", "")
            outputs = status_json.get("outputs", [])

            if status == "completed" and outputs:
                img_url = outputs[0].get("url")
                if img_url:
                    await update.message.reply_photo(img_url)
                    return

            await asyncio.sleep(4)

        await update.message.reply_text("Job still processing. Try again later.")

    except Exception as e:
        await update.message.reply_text(f"txt2img error: {e}")

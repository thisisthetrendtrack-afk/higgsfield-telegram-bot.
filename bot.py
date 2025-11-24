import os
import asyncio
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ApplicationBuilder,
    filters,
)
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from higgsfield_api import HiggsfieldAPI
from nano_banana_api import NanoBananaAPI
import requests

# -----------------------------
# GLOBAL MEMORY
# -----------------------------
global_memory = {}  # user_id -> { mode: "text" | "banana", prompt: "" }

# -----------------------------
# COMMAND: /start
# -----------------------------
async def start(update, context):
    user_id = update.message.from_user.id

    keyboard = [
        [
            InlineKeyboardButton("🎨 Text → Image (Higgsfield)", callback_data="mode_text"),
        ],
        [
            InlineKeyboardButton("🍌 Text → Image (Nano Pro)", callback_data="mode_banana"),
        ]
    ]

    await update.message.reply_text(
        "👋 Welcome! Choose a generation mode:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# -----------------------------
# MODE SWITCH HANDLER
# -----------------------------
async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in global_memory:
        global_memory[user_id] = { "mode": None, "prompt": "" }

    if query.data == "mode_text":
        global_memory[user_id]["mode"] = "text"
        await query.edit_message_text(
            "🎨 *Text → Image (Higgsfield)* selected!\nSend me a prompt.",
            parse_mode="Markdown",
        )

    elif query.data == "mode_banana":
        global_memory[user_id]["mode"] = "banana"
        await query.edit_message_text(
            "🍌 *Nano Pro Text → Image* selected!\nSend me a prompt.",
            parse_mode="Markdown",
        )


# -----------------------------
# TEXT HANDLER
# -----------------------------
async def message_handler(update, context):
    user_id = update.message.from_user.id

    if user_id not in global_memory:
        await update.message.reply_text("❗ Please choose a mode first using /start")
        return

    mode = global_memory[user_id]["mode"]
    prompt = update.message.text
    global_memory[user_id]["prompt"] = prompt

    # -----------------------------
    # HIGGSFIELD TEXT TO IMAGE
    # -----------------------------
    if mode == "text":
        await update.message.reply_text("⏳ Generating your image with Higgsfield...")

        api = HiggsfieldAPI()
        result = api.create_generation(prompt=prompt, mode="text_to_image")

        if "id" not in result:
            await update.message.reply_text("❌ Failed to start generation.")
            return

        gen_id = result["id"]

        # Polling
        while True:
            final = api.check_generation(gen_id)
            if final.get("status") == "completed":
                break
            await asyncio.sleep(2)

        # Send image
        url = final.get("image_url")
        if url:
            photo = requests.get(url).content
            await update.message.reply_photo(photo)
            await update.message.reply_text(
                "🎉 Your Higgsfield image is ready!"
            )
        else:
            await update.message.reply_text("❌ Failed to get image URL")

    # -----------------------------
    # NANO BANANA TEXT TO IMAGE
    # -----------------------------
    elif mode == "banana":
        await update.message.reply_text("🍌 Generating with Nano Banana Pro...")

        api = NanoBananaAPI()
        task = api.create_task(prompt=prompt)

        if task.get("code") != 200:
            await update.message.reply_text("❌ Failed to create Nano Pro task.")
            return

        task_id = task["data"]["taskId"]

        # Polling
        import json
        while True:
            info = api.check_task(task_id)
            state = info["data"]["state"]

            if state == "success":
                break
            elif state == "fail":
                await update.message.reply_text("❌ Nano Pro generation failed.")
                return

            await asyncio.sleep(2)

        # Parse result
        result_json = json.loads(info["data"]["resultJson"])
        url = result_json["resultUrls"][0]

        image = requests.get(url).content
        await update.message.reply_photo(image)

        await update.message.reply_text("🍌✨ Your Nano Pro image is ready!")


# -----------------------------
# REGISTER
# -----------------------------
def register_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

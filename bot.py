"""
Telegram bot handlers and business logic.

This module contains the asynchronous handlers for commands and messages
received by the Telegram bot. The primary feature implemented here is
the DoP (Directors of Photography) image‑to‑video workflow using the
Higgsfield API. Users upload an image and then send a prompt; the bot
creates a job with Higgsfield, polls its status and returns the final
video. Placeholder handlers are provided for additional commands that
aren't yet implemented.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CallbackContext,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

from utils import extract_image_url


logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command.

    Greets the user and provides a short overview of how to use the bot.
    """
    message = (
        "👋 Hello! I'm your Higgsfield video assistant.\n\n"
        "To convert an image into a short cinematic video, follow these steps:\n"
        "1. Use /image2video to begin.\n"
        "2. Upload a photo.\n"
        "3. Send a text prompt describing the motion you want.\n\n"
        "I'll generate a video for you using Higgsfield's DoP model and send it back when it's ready."
    )
    await update.message.reply_text(message)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command.

    Provides a summary of available commands and their usage.
    """
    message = (
        "Here are the commands you can use:\n"
        "/start – Start the bot and see a welcome message.\n"
        "/help – Display this help message.\n"
        "/image2video – Begin an image‑to‑video job.\n"
        "/status <job_id> – Check the status of an existing job.\n"
        "/delete_character <id> – Placeholder command.\n"
        "/speak, /soul, /motions, /characters – Placeholder commands for future features."
    )
    await update.message.reply_text(message)


async def image2video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /image2video command.

    Instructs the user to upload an image and then send a prompt. Resets any
    previously stored image URL to ensure a new job is started.
    """
    context.user_data.pop("image_url", None)
    context.user_data.pop("job_set_id", None)
    await update.message.reply_text(
        "Please upload a photo. After the upload finishes, send a text prompt "
        "describing the motion you would like to see in the video."
    )


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming photos.

    Stores the photo's file path URL in ``user_data['image_url']`` for later use.
    Only the highest resolution photo in the list is used.
    """
    if not update.message or not update.message.photo:
        return

    # Extract the file URL via the helper in utils. Telegram stores
    # multiple sizes; the last element is the largest.
    try:
        file = update.message.photo[-1]
        image_url = await extract_image_url(file)
    except Exception as exc:  # Broad catch because network errors can be varied
        logger.exception("Failed to retrieve image URL: %s", exc)
        await update.message.reply_text(
            "Sorry, I couldn't read that image. Please try uploading it again."
        )
        return

    # Save the image URL to user_data so the next text message can trigger
    # the generation job.
    context.user_data["image_url"] = image_url

    await update.message.reply_text(
        "Image received! Now send me a prompt describing what should happen in the video."
    )


async def prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle plain text messages (prompts).

    If the user has previously uploaded an image, this function will create
    a DoP job via the Higgsfield API. It then spawns a background task to
    poll for job completion and notify the user when the video is ready.
    Otherwise it instructs the user to start with /image2video and upload
    an image first.
    """
    # Ignore commands (they are handled separately). Only treat pure text
    # messages as prompts.
    if update.message is None or update.message.text is None:
        return

    image_url: Optional[str] = context.user_data.get("image_url")
    if not image_url:
        # The user hasn't uploaded an image yet. Provide guidance.
        await update.message.reply_text(
            "Please start by using /image2video and uploading an image first."
        )
        return

    prompt = update.message.text.strip()
    if not prompt:
        await update.message.reply_text(
            "Your prompt appears to be empty. Please describe what should happen in the video."
        )
        return

    # Prevent multiple concurrent jobs for the same user: if a job is already
    # running, ask the user to wait rather than starting another one.
    if context.user_data.get("job_set_id"):
        await update.message.reply_text(
            "A video generation job is already in progress. Please wait for it to complete or use /status <job_id> to check on it."
        )
        return

    # Retrieve the API wrapper from bot_data.
    api = context.bot_data.get("api")
    if api is None:
        logger.error("Higgsfield API wrapper not available in bot_data")
        await update.message.reply_text("Internal configuration error. Please try again later.")
        return

    await update.message.reply_text("Creating your video… this might take a minute.")

    # Create the job in a thread to avoid blocking the event loop. ``asyncio.to_thread``
    # will run the synchronous ``create_dop_job`` method in a worker thread.
    try:
        job_set_id, _job_data = await asyncio.to_thread(api.create_dop_job, image_url, prompt)
    except Exception as exc:
        logger.exception("Failed to create DoP job: %s", exc)
        await update.message.reply_text(
            "Sorry, I couldn't create the video job. Please try again later or verify your HF_KEY and HF_SECRET."
        )
        return

    if not job_set_id:
        await update.message.reply_text(
            "Unexpected response from the Higgsfield API – no job ID returned."
        )
        return

    # Store the job ID so the user can query it later with /status.
    context.user_data["job_set_id"] = job_set_id

    # Launch the polling coroutine as a background task. We don't await it here
    # because we want to return control to the event loop immediately. When
    # the task completes it will notify the user with the result.
    context.application.create_task(
        poll_job(update, context, job_set_id), name=f"poll_job_{job_set_id}"
    )

    await update.message.reply_text(f"Your job ID is {job_set_id}. I'll notify you when it's done.")


async def poll_job(update: Update, context: ContextTypes.DEFAULT_TYPE, job_set_id: str) -> None:
    """Poll the Higgsfield API for job completion.

    This coroutine repeatedly checks the status of a job every four seconds.
    When the job completes successfully it sends the resulting video to the
    user. If the job fails or is flagged as NSFW, an error message is sent
    instead. The stored ``job_set_id`` is cleared afterwards so the user can
    start another job.

    Args:
        update: The original update that triggered the job creation. Used to
            reply back to the same chat.
        context: The callback context containing the bot data and user data.
        job_set_id: The identifier returned by the Higgsfield API when the job
            was created.
    """
    api = context.bot_data.get("api")
    chat_id = update.effective_chat.id if update.effective_chat else None

    # Keep polling until we break out of the loop.
    while True:
        try:
            job_data = await asyncio.to_thread(api.get_job_status, job_set_id)
        except Exception as exc:
            logger.exception("Failed to poll job status: %s", exc)
            if chat_id:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Error while polling job status. I'll keep trying…",
                )
            await asyncio.sleep(4)
            continue

        # Determine the current status. The Higgsfield API may return status
        # information either at the root or inside the jobs list. We attempt
        # to extract the status from both locations.
        status: Optional[str] = None
        if isinstance(job_data, dict):
            status = job_data.get("status") or job_data.get("job_set_status")
            jobs = job_data.get("jobs") or job_data.get("data") or []
        else:
            jobs = []

        if not status and jobs:
            # Use the status of the first job if available.
            first_job = jobs[0]
            status = first_job.get("status")

        # Normalise status for comparison
        normalized = status.lower() if status else "pending"

        if normalized in {"completed", "succeeded", "success", "finished", "done"}:
            # Attempt to extract the video URL. The structure of the API
            # response isn't documented publicly, so we check a few common
            # locations: job['raw']['url'] or job['output']['raw']['url'].
            video_url: Optional[str] = None
            for job in jobs:
                # Each job may have a 'raw' dict containing the final video URL.
                raw = job.get("raw") or {}
                if isinstance(raw, dict):
                    video_url = raw.get("url") or raw.get("video_url")
                # Some APIs nest raw inside output
                if not video_url:
                    output = job.get("output") or {}
                    raw2 = output.get("raw") or {}
                    if isinstance(raw2, dict):
                        video_url = raw2.get("url")
                if video_url:
                    break
            if video_url:
                try:
                    await context.bot.send_video(chat_id=chat_id, video=video_url)
                except Exception as exc:
                    logger.exception("Failed to send video: %s", exc)
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="Video generation completed but I couldn't send the video."
                    )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="Video generation succeeded but no video URL was found in the response."
                )
            # Clear the job ID so the user can start another job.
            context.user_data.pop("job_set_id", None)
            return
        elif normalized in {"failed", "error", "nsfw", "rejected"}:
            # Extract a reason if available
            message = job_data.get("message") or job_data.get("error") or "The job failed or was flagged as NSFW."
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Generation failed: {message}"
            )
            context.user_data.pop("job_set_id", None)
            return
        else:
            # Not finished yet – wait and poll again
            await asyncio.sleep(4)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /status command.

    Allows a user to query the status of a job by providing its job set ID as
    the first argument. If no ID is provided, the command will report the
    status of the most recent job started by the user (if any).
    """
    api = context.bot_data.get("api")
    if api is None:
        await update.message.reply_text("Internal configuration error.")
        return

    # Determine which job ID to check. The user can supply it as a
    # command argument (e.g. /status abc123). Fallback to the stored
    # job_set_id for the user.
    args = context.args
    job_set_id: Optional[str] = args[0] if args else context.user_data.get("job_set_id")
    if not job_set_id:
        await update.message.reply_text("No job ID provided and no recent job found.")
        return

    try:
        job_data = await asyncio.to_thread(api.get_job_status, job_set_id)
    except Exception as exc:
        logger.exception("Failed to fetch job status: %s", exc)
        await update.message.reply_text("Could not retrieve job status. Please try again later.")
        return

    # Try to extract a status string
    status = job_data.get("status") or job_data.get("job_set_status")
    if not status and job_data.get("jobs"):
        status = job_data["jobs"][0].get("status")
    status_text = status or "unknown"
    await update.message.reply_text(f"Status of job {job_set_id}: {status_text}")


async def speak_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Placeholder for the /speak command."""
    await update.message.reply_text("/speak is not implemented yet. Stay tuned!")


async def soul_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Placeholder for the /soul command."""
    await update.message.reply_text("/soul is not implemented yet. Stay tuned!")


async def motions_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Placeholder for the /motions command."""
    await update.message.reply_text("/motions is not implemented yet. Stay tuned!")


async def characters_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Placeholder for the /characters command."""
    await update.message.reply_text("/characters is not implemented yet. Stay tuned!")


async def delete_character_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Placeholder for the /delete_character command."""
    await update.message.reply_text("/delete_character is not implemented yet. Stay tuned!")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler for unhandled exceptions.

    Logs the exception and notifies the user that an error has occurred. Even
    unexpected exceptions should not crash the bot; this handler helps keep
    the bot running in production.
    """
    logger.exception("Unhandled exception while handling an update: %s", context.error)
    try:
        if update and isinstance(update, Update) and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="An unexpected error occurred. Please try again later."
            )
    except Exception:
        # Ignore any exceptions raised while trying to notify the user.
        pass


def register_handlers(application: Application) -> None:
    """Register all command and message handlers on the given application."""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("image2video", image2video))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("speak", speak_command))
    application.add_handler(CommandHandler("soul", soul_command))
    application.add_handler(CommandHandler("motions", motions_command))
    application.add_handler(CommandHandler("characters", characters_command))
    application.add_handler(CommandHandler("delete_character", delete_character_command))

    # Photo handler must come before the text handler so that photos don't fall
    # through to the prompt handler.
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    # Treat any text that isn't a command as a prompt for the image2video job.
    application.add_handler(
        MessageHandler(filters.TEXT & (~filters.COMMAND), prompt_handler)
    )

    # Register the global error handler.
    application.add_error_handler(error_handler)
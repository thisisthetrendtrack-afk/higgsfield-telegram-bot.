import os
import aiohttp
from telegram import Bot

async def download_file(bot: Bot, file_id: str) -> str:
    """
    Downloads a Telegram file properly using bot.get_file()
    Returns local file path.
    """

    # Create folder
    os.makedirs("downloads", exist_ok=True)

    # Telegram get file
    file = await bot.get_file(file_id)
    file_path = f"downloads/{file_id}.jpg"

    # FULL download URL
    download_url = file.file_path

    async with aiohttp.ClientSession() as session:
        async with session.get(download_url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to download file: {resp.status}")

            with open(file_path, "wb") as f:
                f.write(await resp.read())

    return file_path

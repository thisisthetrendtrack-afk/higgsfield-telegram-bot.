# utils.py

import aiohttp
import os

async def download_file(url: str, save_path: str) -> str:
    """
    Download any file from Telegram download URL.
    """
    folder = os.path.dirname(save_path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Download failed: {resp.status}")
            data = await resp.read()

    with open(save_path, "wb") as f:
        f.write(data)

    return save_path


async def get_telegram_file_url(bot, file_id: str) -> str:
    """
    Telegram API gives direct file link.
    """
    tg_file = await bot.get_file(file_id)
    return tg_file.file_path

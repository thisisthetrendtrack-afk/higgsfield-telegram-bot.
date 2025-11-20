import aiohttp
import os


async def download_file(file_url: str, local_path: str = None) -> str:
    """
    Download a file from a given URL and save locally.
    """
    if local_path is None:
        folder = "downloads"
        os.makedirs(folder, exist_ok=True)
        local_path = f"{folder}/{os.path.basename(file_url)}"

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed to download file: HTTP {resp.status}")
            data = await resp.read()

    with open(local_path, "wb") as f:
        f.write(data)

    return local_path


async def get_telegram_file_url(bot, file_id: str) -> str:
    """
    Convert Telegram file_id into a downloadable URL.
    """
    tg_file = await bot.get_file(file_id)
    return tg_file.file_path

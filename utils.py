import aiohttp
import os


async def download_file(url: str, save_path: str) -> str:
    """
    Downloads a file from Telegram URL and saves it locally.
    """
    if not os.path.exists(os.path.dirname(save_path)):
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Download failed: {resp.status}")
            data = await resp.read()

            with open(save_path, "wb") as f:
                f.write(data)

    return save_path


async def get_file_url(bot, file_id: str) -> str:
    """
    Returns usable download URL from Telegram file_id.
    """
    file = await bot.get_file(file_id)
    return file.file_path

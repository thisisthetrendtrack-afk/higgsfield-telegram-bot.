import os
import aiohttp

async def download_file(file_obj):
    """
    Downloads a Telegram file to local storage and returns its file path.
    """
    file_path = f"downloads/{file_obj.file_id}.jpg"

    os.makedirs("downloads", exist_ok=True)

    async with aiohttp.ClientSession() as session:
        async with session.get(file_obj.file_path) as resp:
            if resp.status != 200:
                raise Exception("Failed to download file")

            with open(file_path, "wb") as f:
                f.write(await resp.read())

    return file_path

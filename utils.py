import os
import requests

async def download_file(file_obj, bot):
    """
    Downloads a Telegram file using bot.get_file()
    and returns local file path.
    """
    # Make download folder
    os.makedirs("downloads", exist_ok=True)

    # Telegram file URL
    file = await bot.get_file(file_obj.file_id)
    file_url = file.file_path  # direct URL

    # Local path
    file_path = f"downloads/{file_obj.file_unique_id}.jpg"

    # Download using requests (sync)
    r = requests.get(file_url)
    if r.status_code != 200:
        raise Exception("Failed to download Telegram file")

    with open(file_path, "wb") as f:
        f.write(r.content)

    return file_path

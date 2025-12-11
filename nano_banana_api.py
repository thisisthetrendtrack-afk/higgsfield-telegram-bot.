import os
import requests
import base64

class NanoBananaError(Exception):
    pass

MODELSLAB_ENDPOINT = "https://modelslab.com/api/v7/images/text-to-image"
DEFAULT_MODEL = "nano-banana-pro"

def generate_nano_image(prompt: str, size: str = "1024x1024", timeout: int = 60) -> bytes:
    api_key = os.getenv("NANO_BANANA_API_KEY")
    if not api_key:
        raise NanoBananaError("Missing NANO_BANANA_API_KEY env variable")

    payload = {
        "key": api_key,           # REQUIRED
        "model": DEFAULT_MODEL,   # Required model
        "prompt": prompt,
        "size": size
    }

    headers = {
        "Content-Type": "application/json"
    }

    resp = requests.post(MODELSLAB_ENDPOINT, json=payload, headers=headers, timeout=timeout)

    # Handle errors
    if resp.status_code != 200:
        raise NanoBananaError(f"HTTP {resp.status_code}: {resp.text}")

    data = resp.json()

    # Most ModelsLab responses look like: { "images": ["base64string"] }
    if "images" in data and len(data["images"]) > 0:
        img_b64 = data["images"][0]
        try:
            return base64.b64decode(img_b64)
        except Exception:
            raise NanoBananaError("Image returned but unable to decode Base64")

    raise NanoBananaError(f"Unexpected response: {data}")

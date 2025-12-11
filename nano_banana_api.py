import os
import requests
import base64

class NanoBananaError(Exception):
    pass

ENDPOINT = "https://modelslab.com/api/v7/images/text-to-image"

def generate_nano_image(prompt: str, size: str = "1024x1024", timeout: int = 60) -> bytes:
    api_key = os.getenv("NANO_BANANA_API_KEY")
    if not api_key:
        raise NanoBananaError("Missing NANO_BANANA_API_KEY environment variable")

    payload = {
        "key": api_key,                 # REQUIRED
        "model_id": "nano-banana-pro",  # REQUIRED
        "prompt": prompt,
        "size": size
    }

    headers = {"Content-Type": "application/json"}

    resp = requests.post(ENDPOINT, json=payload, headers=headers, timeout=timeout)

    # Basic error handling
    if resp.status_code != 200:
        try:
            data = resp.json()
            raise NanoBananaError(f"API error: {data}")
        except:
            raise NanoBananaError(f"HTTP error {resp.status_code}: {resp.text}")

    # Parse JSON
    data = resp.json()

    # ModelsLab returns: { "images": ["<base64string>"] }
    if "images" in data and isinstance(data["images"], list) and len(data["images"]) > 0:
        b64 = data["images"][0]
        try:
            return base64.b64decode(b64)
        except:
            raise NanoBananaError("Failed to decode base64 image")

    raise NanoBananaError(f"Unexpected response: {data}")

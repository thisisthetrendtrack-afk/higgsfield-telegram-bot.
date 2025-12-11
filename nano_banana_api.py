# nano_banana_api.py
# Simple ModelsLab Nano Banana text-to-image API wrapper

import os
import requests
import base64


class NanoBananaError(Exception):
    pass


MODELSLAB_ENDPOINT = "https://modelslab.com/api/v7/images/text-to-image"


def generate_nano_image(prompt: str, size: str = "1024x1024") -> bytes:
    """
    Generate an image using ModelsLab Nano Banana Pro.
    Returns raw image bytes.
    """

    api_key = os.getenv("NANO_BANANA_API_KEY")
    if not api_key:
        raise NanoBananaError("Missing NANO_BANANA_API_KEY environment variable")

    payload = {
        "model": "nano-banana-pro",
        "prompt": prompt,
        "size": size
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        MODELSLAB_ENDPOINT,
        json=payload,
        headers=headers,
        timeout=60
    )

    if response.status_code != 200:
        try:
            return response.json()
        except:
            raise NanoBananaError(f"API error: {response.text}")

    data = response.json()

    # --- HANDLE ALL POSSIBLE MODELSLAB RESPONSES ---

    # Case 1: direct base64 field
    if "image_base64" in data:
        return base64.b64decode(data["image_base64"])

    # Case 2: images: [{ b64 }]
    if "images" in data and isinstance(data["images"], list):
        first = data["images"][0]
        if "b64" in first:
            return base64.b64decode(first["b64"])
        if "url" in first:
            img = requests.get(first["url"])
            return img.content

    # Case 3: data: [{ b64_json }]
    if "data" in data:
        first = data["data"][0]
        if "b64_json" in first:
            return base64.b64decode(first["b64_json"])
        if "url" in first:
            img = requests.get(first["url"])
            return img.content

    raise NanoBananaError("Unexpected API response – no image found")

# nano_banana_edit_api.py
import os
import requests

MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")

class NanoBananaEditError(Exception):
    pass

def generate_nano_image_edit(prompt: str, image_urls: list):
    if not MODELSLAB_KEY:
        raise NanoBananaEditError("MODELSLAB_KEY not set")

    payload = {
        "prompt": prompt,
        "model_id": "nano-banana-pro",
        "init_image": image_urls,
        "aspect_ratio": "1:1",
        "key": MODELSLAB_KEY,
    }

    r = requests.post(
        "https://modelslab.com/api/v7/images/image-to-image",
        json=payload,
        timeout=300,
    )

    if r.status_code != 200:
        raise NanoBananaEditError(f"HTTP {r.status_code}: {r.text}")

    data = r.json()

    if data.get("status") != "success":
        raise NanoBananaEditError(data)

    output = data.get("output")
    if not output or not isinstance(output, list):
        raise NanoBananaEditError("No output image returned")

    return output[0]  # image URL

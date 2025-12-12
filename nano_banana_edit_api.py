# nano_banana_edit_api.py
import os
import time
import requests
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ENDPOINT = os.getenv("NANO_BANANA_EDIT_ENDPOINT", "https://modelslab.com/api/v7/images/image-to-image")
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")  # same key used for hailuo
MODEL_ID = os.getenv("NANO_BANANA_PRO_MODEL")  # required: exact model id for nano banana pro
DEFAULT_TIMEOUT = int(os.getenv("NANO_BANANA_TIMEOUT", "240"))  # seconds

class NanoBananaEditError(Exception):
    pass

def _download_url(url: str, timeout=300) -> bytes:
    logger.info("Downloading asset: %s", url)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content

def _extract_link(obj: dict) -> Optional[str]:
    # look for common keys
    for key in ("image_url", "output", "output_url", "result", "url"):
        v = obj.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
        if isinstance(v, list) and v and isinstance(v[0], str) and v[0].startswith("http"):
            return v[0]
    # future_links pattern
    fl = obj.get("future_links")
    if isinstance(fl, list) and fl:
        if isinstance(fl[0], str) and fl[0].startswith("http"):
            return fl[0]
    # nested fields
    data = obj.get("data")
    if isinstance(data, dict):
        return _extract_link(data)
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return _extract_link(first)
    return None

def generate_nano_edit_image(image_bytes: bytes, prompt: str, size: Optional[str] = None, model_id: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bytes, str]:
    """
    Send image + prompt to ModelsLab image-to-image endpoint.
    Returns: (image_bytes, final_url)
    Raises NanoBananaEditError on failure.
    """
    if not MODELSLAB_KEY:
        raise NanoBananaEditError("Missing MODELSLAB_KEY env variable")
    model = model_id or MODEL_ID
    if not model:
        raise NanoBananaEditError("Missing NANO_BANANA_PRO_MODEL env variable (exact model id)")

    files = {
        "image": ("image.png", image_bytes, "image/png")
    }
    payload = {
        "key": MODELSLAB_KEY,
        "model_id": model,
        "prompt": prompt
    }
    if size:
        payload["size"] = size

    # first POST - send multipart with image
    try:
        resp = requests.post(ENDPOINT, data=payload, files=files, timeout=60)
    except Exception as e:
        raise NanoBananaEditError(f"Failed to POST to ModelsLab image-to-image endpoint: {e}")

    # parse json
    try:
        data = resp.json()
    except Exception:
        # maybe direct bytes returned (rare)
        ct = resp.headers.get("Content-Type", "")
        if ct.startswith("image/") or ct == "application/octet-stream":
            return resp.content, "<direct-response>"
        raise NanoBananaEditError(f"Non-JSON response from ModelsLab: HTTP {resp.status_code} - {resp.text[:1000]}")

    # if immediate error
    if isinstance(data, dict) and data.get("status") == "error":
        raise NanoBananaEditError(f"ModelsLab API error: {data}")

    # if immediate success and URL present
    if isinstance(data, dict) and data.get("status") in ("success", "completed"):
        link = _extract_link(data)
        if not link:
            raise NanoBananaEditError(f"No image URL found in success response: {data}")
        final_bytes = _download_url(link, timeout=timeout)
        return final_bytes, link

    # if processing -> poll fetch_result (same pattern as hailuo)
    if isinstance(data, dict) and data.get("status") == "processing":
        fetch_url = data.get("fetch_result")
        eta = int(data.get("eta", 3) or 3)
        if not fetch_url:
            raise NanoBananaEditError(f"Processing response missing fetch_result: {data}")
        # wait ETA then poll
        time.sleep(min(max(1, eta), 30))
        deadline = time.time() + timeout
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            try:
                poll_resp = requests.post(fetch_url, json={"key": MODELSLAB_KEY}, timeout=30)
                poll_resp.raise_for_status()
                j = poll_resp.json()
            except Exception as e:
                # backoff
                time.sleep(min(2 + attempt, 8))
                continue
            if isinstance(j, dict) and j.get("status") == "error":
                raise NanoBananaEditError(f"NanoBanana fetch error: {j}")
            if isinstance(j, dict) and j.get("status") in ("success", "completed"):
                link = _extract_link(j)
                if not link:
                    raise NanoBananaEditError(f"No final image link in fetch response: {j}")
                b = _download_url(link, timeout=timeout)
                return b, link
            # not ready yet
            time.sleep(2)
        raise NanoBananaEditError("Timeout waiting for ModelsLab image-to-image result")

    raise NanoBananaEditError(f"Unexpected response: {data}")

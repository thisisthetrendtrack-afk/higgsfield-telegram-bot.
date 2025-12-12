# nano_banana_edit_api.py
import os
import time
import requests
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ENDPOINT = os.getenv("NANO_BANANA_EDIT_ENDPOINT", "https://modelslab.com/api/v7/images/image-to-image")
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")
MODEL_ID = os.getenv("NANO_BANANA_PRO_MODEL")  # must be 'nano-banana-pro' per ModelsLab page
DEFAULT_TIMEOUT = int(os.getenv("NANO_BANANA_TIMEOUT", "240"))  # seconds

class NanoBananaEditError(Exception):
    pass

def _download_url(url: str, timeout=300) -> bytes:
    logger.info("Downloading asset: %s", url)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content

def _pick_link(data: dict) -> Optional[str]:
    # common keys where ModelsLab may put the final URL
    for key in ("image_url", "output", "output_url", "result", "url", "future_links"):
        if key in data:
            val = data[key]
            if isinstance(val, str) and val.startswith("http"):
                return val
            if isinstance(val, list) and val:
                if isinstance(val[0], str) and val[0].startswith("http"):
                    return val[0]
    # nested possibilities
    if "data" in data and isinstance(data["data"], dict):
        return _pick_link(data["data"])
    return None

def generate_nano_edit_image(init_image_url: str, prompt: str, size: Optional[str] = None,
                             model_id: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bytes, str]:
    """
    Call ModelsLab image-to-image endpoint using a public init_image URL.
    Returns: (image_bytes, final_url)
    Raises NanoBananaEditError on failure.
    """
    if not MODELSLAB_KEY:
        raise NanoBananaEditError("Missing MODELSLAB_KEY env variable")
    model = model_id or MODEL_ID
    if not model:
        raise NanoBananaEditError("Missing NANO_BANANA_PRO_MODEL env variable (exact model id)")

    payload = {
        "key": MODELSLAB_KEY,
        "model_id": model,
        "init_image": init_image_url,
        "prompt": prompt
    }
    if size:
        payload["size"] = size

    # Submit job
    try:
        resp = requests.post(ENDPOINT, json=payload, timeout=60)
    except Exception as e:
        raise NanoBananaEditError(f"Failed to submit to ModelsLab: {e}")

    try:
        data = resp.json()
    except Exception:
        # If ModelsLab returned an image directly (unlikely), handle it
        ct = resp.headers.get("Content-Type", "")
        if ct.startswith("image/") or ct == "application/octet-stream":
            return resp.content, "<direct-response>"
        raise NanoBananaEditError(f"Non-JSON response from ModelsLab: HTTP {resp.status_code} - {resp.text[:1000]}")

    # immediate error
    if isinstance(data, dict) and data.get("status") == "error":
        raise NanoBananaEditError(f"ModelsLab API error: {data}")

    # immediate success with URL
    if isinstance(data, dict) and data.get("status") in ("success", "completed"):
        link = _pick_link(data)
        if not link:
            raise NanoBananaEditError(f"No image URL found in success response: {data}")
        final_bytes = _download_url(link, timeout=timeout)
        return final_bytes, link

    # processing -> poll fetch_result (use POST)
    if isinstance(data, dict) and data.get("status") == "processing":
        fetch_url = data.get("fetch_result")
        eta = int(data.get("eta", 3) or 3)
        if not fetch_url:
            raise NanoBananaEditError(f"Processing response missing fetch_result: {data}")

        # wait initial ETA
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
                logger.warning("Poll attempt %d failed: %s", attempt, e)
                time.sleep(min(2 + attempt, 8))
                continue

            if isinstance(j, dict) and j.get("status") == "error":
                raise NanoBananaEditError(f"NanoBanana fetch error: {j}")

            if isinstance(j, dict) and j.get("status") in ("success", "completed"):
                link = _pick_link(j)
                if not link:
                    raise NanoBananaEditError(f"No final image link in fetch response: {j}")
                b = _download_url(link, timeout=timeout)
                return b, link

            # still processing
            time.sleep(2)

        raise NanoBananaEditError("Timeout waiting for ModelsLab image-to-image result")

    raise NanoBananaEditError(f"Unexpected response: {data}")

# nano_banana_edit_api.py
import os
import time
import requests
from typing import Optional, Tuple

MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")
MODEL_ID = os.getenv("NANO_BANANA_PRO_MODEL")
ENDPOINT = os.getenv("NANO_BANANA_EDIT_ENDPOINT", "https://modelslab.com/api/v7/images/image-to-image")
DEFAULT_TIMEOUT = int(os.getenv("NANO_BANANA_TIMEOUT", "240"))

class NanoBananaEditError(Exception):
    pass

def _download_url(url: str, timeout=300) -> bytes:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.content

def _pick_link(data: dict):
    for k in ("image_url","output","output_url","result","url"):
        v = data.get(k)
        if isinstance(v, str) and v.startswith("http"):
            return v
        if isinstance(v, list) and v and isinstance(v[0], str) and v[0].startswith("http"):
            return v[0]
    if isinstance(data.get("data"), dict):
        return _pick_link(data["data"])
    return None

def generate_nano_edit_image(init_image_url: str, prompt: str, size: Optional[str] = None,
                             model_id: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bytes, str]:
    """
    Submit a JSON job to ModelsLab using 'init_image' (a public URL string).
    Returns (image_bytes, final_url) or raises NanoBananaEditError.
    """
    if not MODELSLAB_KEY:
        raise NanoBananaEditError("Missing MODELSLAB_KEY")
    model = model_id or MODEL_ID
    if not model:
        raise NanoBananaEditError("Missing NANO_BANANA_PRO_MODEL")

    payload = {
        "key": MODELSLAB_KEY,
        "model_id": model,
        "init_image": init_image_url,
        "prompt": prompt
    }
    if size:
        payload["size"] = size

    try:
        resp = requests.post(ENDPOINT, json=payload, timeout=60)
    except Exception as e:
        raise NanoBananaEditError(f"Failed to submit to ModelsLab: {e}")

    try:
        j = resp.json()
    except Exception:
        ct = resp.headers.get("Content-Type","")
        if ct.startswith("image/"):
            return resp.content, "<direct>"
        raise NanoBananaEditError(f"Non-JSON response: {resp.status_code}")

    if isinstance(j, dict) and j.get("status") == "error":
        raise NanoBananaEditError(f"ModelsLab API error: {j}")

    if isinstance(j, dict) and j.get("status") in ("success","completed"):
        link = _pick_link(j)
        if not link:
            raise NanoBananaEditError(f"No URL in success response: {j}")
        return _download_url(link, timeout), link

    if isinstance(j, dict) and j.get("status") == "processing":
        fetch_url = j.get("fetch_result")
        if not fetch_url:
            raise NanoBananaEditError(f"Missing fetch_result: {j}")
        # poll with POST (ModelsLab expects POST)
        deadline = time.time() + timeout
        # small initial wait if eta present
        eta = int(j.get("eta", 2) or 2)
        time.sleep(min(max(1, eta), 30))
        while time.time() < deadline:
            try:
                poll = requests.post(fetch_url, json={"key": MODELSLAB_KEY}, timeout=30)
                poll.raise_for_status()
                pj = poll.json()
            except Exception:
                time.sleep(2)
                continue
            if isinstance(pj, dict) and pj.get("status") == "error":
                raise NanoBananaEditError(f"Fetch error: {pj}")
            if isinstance(pj, dict) and pj.get("status") in ("success","completed"):
                link = _pick_link(pj)
                if not link:
                    raise NanoBananaEditError(f"No link in fetch response: {pj}")
                return _download_url(link, timeout), link
            time.sleep(2)
        raise NanoBananaEditError("Timeout waiting for result")
    raise NanoBananaEditError(f"Unexpected response: {j}")

# sora_api.py
import os
import time
import logging
from typing import Tuple, Optional
import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ENDPOINT = os.getenv("MODELSLAB_ENDPOINT", "https://modelslab.com/api/v7/video-fusion/text-to-video")
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY") or os.getenv("MODELSLAB_API_KEY")
SORA_MODEL = os.getenv("SORA_MODEL", "sora-2")
DEFAULT_TIMEOUT = int(os.getenv("SORA_TIMEOUT", "480"))

class SoraError(Exception):
    pass

def _download_url(url: str, timeout: int = 300) -> bytes:
    try:
        r = requests.get(url, stream=True, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception as e:
        raise SoraError(f"Failed to download asset {url}: {e}")

def _extract_link(j: dict) -> Optional[str]:
    # try known fields
    for key in ("future_links", "video_url", "output", "output_url", "result", "url"):
        val = j.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
        if isinstance(val, list) and val and isinstance(val[0], str) and val[0].startswith("http"):
            return val[0]
        if isinstance(val, list) and val and isinstance(val[0], dict):
            # pick url inside object
            for k in ("url", "video_url", "output"):
                if val[0].get(k) and isinstance(val[0].get(k), str) and val[0].get(k).startswith("http"):
                    return val[0].get(k)
    # nested data/results
    for key in ("data", "results", "artifacts"):
        arr = j.get(key)
        if isinstance(arr, list) and arr:
            first = arr[0]
            if isinstance(first, str) and first.startswith("http"):
                return first
            if isinstance(first, dict):
                for k in ("url", "video_url", "output", "result"):
                    v = first.get(k)
                    if isinstance(v, str) and v.startswith("http"):
                        return v
                    if isinstance(v, list) and v and isinstance(v[0], str) and v[0].startswith("http"):
                        return v[0]
    return None

def generate_sora_video(prompt: str, duration: int = 4, size: str = "1280x720", model_id: str | None = None, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bytes, str]:
    """
    Generate a video via ModelsLab Sora model.
    Returns (video_bytes, final_url).
    Raises SoraError on failure.
    """
    if not MODELSLAB_KEY:
        raise SoraError("Missing MODELSLAB_KEY environment variable")

    model = model_id or SORA_MODEL
    if not model:
        raise SoraError("Missing SORA_MODEL (set env SORA_MODEL)")

    payload = {
        "key": MODELSLAB_KEY,
        "model_id": model,
        "prompt": prompt,
        "duration": str(duration),
        "size": size
    }

    logger.info("Sora request -> model=%s duration=%s size=%s", model, duration, size)
    try:
        resp = requests.post(ENDPOINT, json=payload, timeout=60)
    except Exception as e:
        raise SoraError(f"POST failed: {e}")

    try:
        data = resp.json()
    except Exception:
        content_type = resp.headers.get("Content-Type", "")
        if content_type.startswith("video/") or content_type == "application/octet-stream":
            return resp.content, "<direct-response>"
        raise SoraError(f"Non-JSON response: {resp.status_code} {resp.text[:1000]}")

    # Handle immediate errors
    if isinstance(data, dict) and data.get("status") == "error":
        raise SoraError(f"ModelsLab API error: {data}")

    # immediate success with url
    if isinstance(data, dict) and data.get("status") == "success":
        link = _extract_link(data)
        if not link:
            raise SoraError(f"No URL found in success response: {data}")
        return _download_url(link, timeout=timeout), link

    # processing -> poll fetch_result with POST
    if isinstance(data, dict) and data.get("status") == "processing":
        fetch_url = data.get("fetch_result")
        eta = int(data.get("eta", 3) or 3)
        if not fetch_url:
            raise SoraError(f"Missing fetch_result in processing response: {data}")

        time.sleep(min(max(1, eta), 30))
        deadline = time.time() + timeout
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            try:
                poll_payload = {"key": MODELSLAB_KEY}
                r = requests.post(fetch_url, json=poll_payload, timeout=60)
                r.raise_for_status()
                j = r.json()
            except Exception as e:
                logger.warning("Sora fetch attempt %s failed: %s", attempt, e)
                time.sleep(min(3 + attempt, 8))
                continue

            if isinstance(j, dict) and j.get("status") == "error":
                raise SoraError(f"Sora fetch returned error: {j}")

            if isinstance(j, dict) and j.get("status") in ("success", "completed"):
                link = _extract_link(j)
                if not link:
                    # last fallback: future_links
                    fl = j.get("future_links")
                    if isinstance(fl, list) and fl:
                        link = fl[0]
                if not link:
                    raise SoraError(f"No final link found in fetch response: {j}")
                return _download_url(link, timeout=timeout), link

            eta2 = int(j.get("eta", 3) or 3) if isinstance(j, dict) else 3
            time.sleep(min(max(1, eta2), 8))

        raise SoraError("Timeout waiting for Sora result")

    raise SoraError(f"Unexpected response: {data}")

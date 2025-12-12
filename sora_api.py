# sora_api.py
import os
import time
import logging
from typing import Tuple, Optional, Any
import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Endpoint defaults (can be overridden with env vars)
ENDPOINT = os.getenv("MODELSLAB_ENDPOINT", "https://modelslab.com/api/v7/video-fusion/text-to-video")
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY") or os.getenv("MODELSLAB_API_KEY")
SORA_MODEL = os.getenv("SORA_MODEL", "sora-2")
DEFAULT_TIMEOUT = int(os.getenv("SORA_TIMEOUT", "480"))

class SoraError(Exception):
    pass

def _download_url(url: str, timeout: int = 300) -> bytes:
    """Download a file and return raw bytes, raising SoraError on failure."""
    logger.info("Downloading final asset: %s", url)
    try:
        r = requests.get(url, stream=True, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception as e:
        raise SoraError(f"Failed to download asset {url}: {e}")

def _extract_candidate_link(json_obj: dict) -> Optional[str]:
    """Try multiple common keys/places for a final asset URL."""
    if not isinstance(json_obj, dict):
        return None

    # Direct keys that sometimes contain a URL or a list
    for key in ("video_url", "output_url", "output", "result", "url"):
        v = json_obj.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
        if isinstance(v, list) and v and isinstance(v[0], str) and v[0].startswith("http"):
            return v[0]

    # list-style fields that might contain strings or dicts
    for listname in ("future_links", "outputs", "proxy_links", "output_links", "results", "videos", "artifacts"):
        arr = json_obj.get(listname)
        if isinstance(arr, list) and len(arr) > 0:
            if isinstance(arr[0], str) and arr[0].startswith("http"):
                return arr[0]
            if isinstance(arr[0], dict):
                for candidate in ("url", "video_url", "output", "result"):
                    if arr[0].get(candidate) and isinstance(arr[0].get(candidate), str) and arr[0].get(candidate).startswith("http"):
                        return arr[0].get(candidate)

    # nested 'data' or first element of 'data' might have url
    for arrkey in ("data", "results"):
        arr = json_obj.get(arrkey)
        if isinstance(arr, list) and len(arr) > 0:
            first = arr[0]
            if isinstance(first, dict):
                for k in ("url", "video_url", "output", "result", "future_links"):
                    v = first.get(k)
                    if isinstance(v, str) and v.startswith("http"):
                        return v
                    if isinstance(v, list) and len(v) > 0 and isinstance(v[0], str) and v[0].startswith("http"):
                        return v[0]

    return None

def generate_sora_video(
    prompt: str,
    duration: int = 4,
    size: str = "1280x720",
    model_id: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
    return_debug: bool = False
) -> Tuple[bytes, str, Optional[Any]]:
    """
    Generate a video via ModelsLab Sora model.

    Args:
      prompt: text prompt
      duration: duration in seconds (string-accepted by API)
      size: "WIDTHxHEIGHT" (controls aspect ratio/resolution)
      model_id: override model id (defaults to env SORA_MODEL)
      timeout: total seconds to wait for job completion (polling)
      return_debug: if True, returns (bytes, final_url, last_fetch_json)
                    otherwise returns (bytes, final_url, None)

    Returns:
      (video_bytes, final_url, last_fetch_json_or_none)

    Raises:
      SoraError on any failure.
    """
    if not MODELSLAB_KEY:
        raise SoraError("Missing MODELSLAB_KEY environment variable")

    model = model_id or SORA_MODEL
    if not model:
        raise SoraError("Missing SORA_MODEL environment variable (set SORA_MODEL)")

    payload = {
        "key": MODELSLAB_KEY,
        "model_id": model,
        "prompt": prompt,
        "duration": str(duration),
        "size": size
    }

    logger.info("Posting Sora request -> model=%s duration=%s size=%s", model, duration, size)
    try:
        resp = requests.post(ENDPOINT, json=payload, timeout=60)
    except Exception as e:
        raise SoraError(f"Failed to POST to ModelsLab endpoint: {e}")

    # Attempt to parse JSON; if non-json and video returned directly, handle
    try:
        data = resp.json()
    except Exception:
        content_type = resp.headers.get("Content-Type", "")
        if content_type.startswith("video/") or content_type == "application/octet-stream":
            return resp.content, "<direct-response>", None
        raise SoraError(f"Non-JSON response from ModelsLab: HTTP {resp.status_code} - {resp.text[:1000]}")

    logger.debug("ModelsLab initial response: %s", data)

    # If immediate error
    if isinstance(data, dict) and data.get("status") == "error":
        raise SoraError(f"ModelsLab API error: {data}")

    # If immediate success with a URL
    if isinstance(data, dict) and data.get("status") in ("success", "completed"):
        link = _extract_candidate_link(data)
        if link:
            video_bytes = _download_url(link, timeout=timeout)
            return (video_bytes, link, data if return_debug else None)
        raise SoraError(f"ModelsLab returned success but no usable video URL found: {data}")

    # If processing, follow fetch_result (ModelsLab uses POST for fetch)
    if isinstance(data, dict) and data.get("status") == "processing":
        fetch_url = data.get("fetch_result")
        eta = int(data.get("eta", 3) or 3)
        start_time = time.time()
        deadline = start_time + timeout

        if not fetch_url:
            raise SoraError(f"Processing response missing fetch_result URL: {data}")

        # initial wait (respect ETA but cap)
        time.sleep(min(max(1, eta), 30))

        last_fetch_json = None
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            try:
                # POST the key to fetch endpoint (ModelsLab requires POST)
                poll_payload = {"key": MODELSLAB_KEY}
                r = requests.post(fetch_url, json=poll_payload, timeout=30)
                r.raise_for_status()
                j = r.json()
                last_fetch_json = j
            except Exception as e:
                logger.warning("Failed to POST fetch_result (attempt %s): %s", attempt, e)
                # backoff & retry
                time.sleep(min(3 + attempt, 10))
                continue

            logger.debug("Fetch_result response (attempt %s): %s", attempt, j)

            # If fetch endpoint reports error -> raise with details
            if isinstance(j, dict) and j.get("status") == "error":
                raise SoraError(f"Sora fetch returned error: {j}")

            # If final success, extract link & download
            if isinstance(j, dict) and j.get("status") in ("success", "completed"):
                link = _extract_candidate_link(j)
                if not link:
                    # fallback: j.get("future_links")
                    fl = j.get("future_links")
                    if isinstance(fl, list) and len(fl) > 0 and isinstance(fl[0], str):
                        link = fl[0]
                if not link:
                    raise SoraError(f"Could not find final video URL in fetch response: {j}")
                video_bytes = _download_url(link, timeout=timeout)
                return (video_bytes, link, last_fetch_json if return_debug else None)

            # Not ready yet: wait and loop. Prefer server-provided ETA if present
            eta2 = int(j.get("eta", 3) or 3) if isinstance(j, dict) else 3
            sleep_time = min(max(1, eta2), 8)
            logger.info("Sora still processing (attempt %s). Sleeping %s sec before next poll.", attempt, sleep_time)
            time.sleep(sleep_time)

        # timeout
        raise SoraError("Timeout waiting for Sora fetch_result to return final video")

    # Unknown response pattern
    raise SoraError(f"Unexpected initial response from ModelsLab: {data}")

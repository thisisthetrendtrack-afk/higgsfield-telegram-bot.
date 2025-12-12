# hailuo_api.py
import os
import time
import logging
from typing import Tuple, Optional
import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ENDPOINT = os.getenv("HAILUO_ENDPOINT", "https://modelslab.com/api/v7/video-fusion/text-to-video")
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY") or os.getenv("MODELSLAB_API_KEY") or os.getenv("HAILUO_API_KEY")
HAILUO_MODEL = os.getenv("HAILUO_MODEL")  # must be exact model id string

# How long (seconds) we'll wait in total for the job (default 8 minutes)
DEFAULT_TIMEOUT = int(os.getenv("HAILUO_TIMEOUT", "480"))

class HailuoError(Exception):
    pass

def _download_url(url: str, timeout: int = 300) -> bytes:
    """Download a file and return raw bytes, raising HailuoError on failure."""
    logger.info("Downloading final asset: %s", url)
    try:
        r = requests.get(url, stream=True, timeout=timeout)
        r.raise_for_status()
        return r.content
    except Exception as e:
        raise HailuoError(f"Failed to download asset {url}: {e}")

def _extract_candidate_link(json_obj: dict) -> Optional[str]:
    """Try multiple common keys/places for a final asset URL."""
    # direct keys
    for key in ("video_url", "output_url", "output", "result", "url"):
        v = json_obj.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], str) and v[0].startswith("http"):
            return v[0]

    # list-style fields that might contain objects
    for listname in ("future_links", "outputs", "proxy_links", "output_links", "results", "videos", "artifacts"):
        arr = json_obj.get(listname)
        if isinstance(arr, list) and len(arr) > 0:
            # if list contains strings, first is probable
            if isinstance(arr[0], str) and arr[0].startswith("http"):
                return arr[0]
            # if list contains dicts, try to find a URL inside dict
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

def generate_hailuo_video(prompt: str, duration: int = 6, size: str = "720x1280", model_id: Optional[str] = None, timeout: int = DEFAULT_TIMEOUT) -> Tuple[bytes, str]:
    """
    Generate a video using ModelsLab Hailuo text->video endpoint.

    Returns (video_bytes, final_url).

    Raises HailuoError on any failure.
    """
    if not MODELSLAB_KEY:
        raise HailuoError("Missing MODELSLAB_KEY environment variable")

    model = model_id or HAILUO_MODEL
    if not model:
        raise HailuoError("Missing HAILUO_MODEL environment variable (set to the exact model id)")

    payload = {
        "key": MODELSLAB_KEY,
        "model_id": model,
        "prompt": prompt,
        "duration": str(duration),
        "size": size
    }

    logger.info("Posting Hailuo request: model=%s duration=%s size=%s", model, duration, size)
    try:
        resp = requests.post(ENDPOINT, json=payload, timeout=60)
    except Exception as e:
        raise HailuoError(f"Failed to POST to ModelsLab endpoint: {e}")

    # try parse JSON
    try:
        data = resp.json()
    except Exception:
        # maybe direct bytes/video returned (rare). If content-type is video, return bytes.
        content_type = resp.headers.get("Content-Type", "")
        if content_type.startswith("video/") or content_type == "application/octet-stream":
            return resp.content, "<direct-response>"
        raise HailuoError(f"Non-JSON response from ModelsLab: HTTP {resp.status_code} - {resp.text[:1000]}")

    logger.debug("ModelsLab initial response: %s", data)

    # If immediate error from API, raise with raw json
    if isinstance(data, dict) and data.get("status") == "error":
        raise HailuoError(f"ModelsLab API error: {data}")

    # If immediate success with an URL inside
    if isinstance(data, dict) and data.get("status") == "success":
        link = _extract_candidate_link(data)
        if link:
            video_bytes = _download_url(link, timeout=timeout)
            return video_bytes, link
        # If success but no URL present, return whole data for debugging
        raise HailuoError(f"ModelsLab returned success but no usable video URL found: {data}")

    # If processing, follow fetch_result polling flow
    if isinstance(data, dict) and data.get("status") == "processing":
        fetch_url = data.get("fetch_result")
        eta = int(data.get("eta", 3) or 3)
        # Respect ETA but don't oversleep beyond timeout
        start_time = time.time()
        deadline = start_time + timeout

        if not fetch_url:
            # Some providers embed job id instead; surface for debugging
            raise HailuoError(f"Processing response missing fetch_result URL: {data}")

        # initial wait for eta seconds (but cap small)
        sleep_first = min(max(1, eta), 30)
        logger.info("ModelsLab job processing: will wait %s seconds before polling fetch_result", sleep_first)
        time.sleep(sleep_first)

        # Poll loop
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            try:
                r = requests.get(fetch_url, timeout=30)
                r.raise_for_status()
                j = r.json()
            except Exception as e:
                logger.warning("Failed to GET fetch_result (attempt %s): %s", attempt, e)
                # backoff a bit and retry
                time.sleep(min(5 + attempt, 10))
                continue

            logger.debug("Fetch_result response (attempt %s): %s", attempt, j)

            # If fetch endpoint reports error
            if isinstance(j, dict) and j.get("status") == "error":
                raise HailuoError(f"Hailuo fetch returned error: {j}")

            # If final success, extract link & download
            if isinstance(j, dict) and j.get("status") in ("success", "completed"):
                link = _extract_candidate_link(j)
                if not link:
                    # fallback: j.get("future_links")
                    fl = j.get("future_links")
                    if isinstance(fl, list) and len(fl) > 0 and isinstance(fl[0], str):
                        link = fl[0]
                if not link:
                    raise HailuoError(f"Could not find final video URL in fetch response: {j}")
                video_bytes = _download_url(link, timeout=timeout)
                return video_bytes, link

            # not ready yet: wait briefly and loop
            # read 'eta' in fetch response if available to wait smarter
            eta2 = int(j.get("eta", 3) or 3) if isinstance(j, dict) else 3
            sleep_time = min(max(1, eta2), 8)
            logger.info("Hailuo still processing (attempt %s). Sleeping %s sec before next poll.", attempt, sleep_time)
            time.sleep(sleep_time)

        # timeout
        raise HailuoError("Timeout waiting for Hailuo fetch_result to return final video")

    # Unknown response pattern: surface for debugging
    raise HailuoError(f"Unexpected initial response from ModelsLab: {data}")

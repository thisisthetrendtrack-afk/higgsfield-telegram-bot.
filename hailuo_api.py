# hailuo_api.py
import os
import requests
import time
import logging

logger = logging.getLogger(__name__)

ENDPOINT = os.getenv("HAILUO_ENDPOINT", "https://modelslab.com/api/v7/video-fusion/text-to-video")
MODELSLAB_KEY = os.getenv("MODELSLAB_KEY") or os.getenv("MODELSLAB_API_KEY") or os.getenv("HAILUO_API_KEY")
HAILUO_MODEL = os.getenv("HAILUO_MODEL")  # REQUIRED: exact model id string from ModelsLab

class HailuoError(Exception):
    pass

def _download_url(url: str, timeout=300) -> bytes:
    r = requests.get(url, stream=True, timeout=timeout)
    if r.status_code != 200:
        raise HailuoError(f"Failed to download asset {url}: HTTP {r.status_code}")
    return r.content

def generate_hailuo_video(prompt: str, duration: int = 6, size: str = "720x1280", model_id: str | None = None, timeout: int = 600) -> bytes:
    """
    Call ModelsLab text->video endpoint and return raw video bytes.
    Requires environment:
      - MODELSLAB_KEY  (your ModelsLab API key)
      - HAILUO_MODEL   (exact model id string — required)
    """
    key = MODELSLAB_KEY
    if not key:
        raise HailuoError("Missing MODELSLAB_KEY environment variable")

    model = model_id or HAILUO_MODEL
    if not model:
        raise HailuoError("Missing HAILUO_MODEL environment variable (set to the exact model id)")

    payload = {
        "key": key,
        "model_id": model,
        "prompt": prompt,
        "duration": str(duration),
        "size": size
    }

    logger.info("Hailuo request -> endpoint=%s model_id=%s duration=%s size=%s", ENDPOINT, model, duration, size)

    resp = requests.post(ENDPOINT, json=payload, timeout=timeout)
    content_type = resp.headers.get("Content-Type", "")
    # Try to parse JSON first (most responses are JSON)
    try:
        data = resp.json()
    except Exception:
        # If response isn't JSON but is video bytes (rare), return directly
        if content_type.startswith("video/") or content_type == "application/octet-stream":
            return resp.content
        raise HailuoError(f"Non-JSON response from ModelsLab: HTTP {resp.status_code} - {resp.text[:1000]}")

    # If ModelsLab reported an error, include whole JSON for debugging
    if isinstance(data, dict) and data.get("status") == "error":
        # return a helpful error with the raw API JSON so you can see 'model_id' messages
        raise HailuoError(f"ModelsLab API error: {data}")

    # Common response patterns:
    # 1) immediate URL field
    for keyname in ("video_url", "output", "output_url", "result", "url"):
        v = data.get(keyname)
        if isinstance(v, str) and v.startswith("http"):
            return _download_url(v)

    # 2) lists with urls
    for listname in ("outputs", "proxy_links", "output_links", "results", "videos"):
        arr = data.get(listname)
        if isinstance(arr, list) and len(arr) > 0 and isinstance(arr[0], str) and arr[0].startswith("http"):
            return _download_url(arr[0])
        if isinstance(arr, list) and len(arr) > 0 and isinstance(arr[0], dict):
            # find url inside dict
            for k in ("url", "video_url", "output"):
                if arr[0].get(k) and isinstance(arr[0].get(k), str) and arr[0].get(k).startswith("http"):
                    return _download_url(arr[0].get(k))

    # 3) nested "data" or "results" arrays
    for arrkey in ("data", "results", "artifacts"):
        arr = data.get(arrkey)
        if isinstance(arr, list) and len(arr) > 0:
            first = arr[0]
            if isinstance(first, dict):
                for k in ("url", "video_url", "output", "result"):
                    if k in first and isinstance(first[k], str) and first[k].startswith("http"):
                        return _download_url(first[k])
            elif isinstance(first, str) and first.startswith("http"):
                return _download_url(first)

    # 4) If the API returned a task id / job id for async processing, surface it so the caller can poll
    if isinstance(data, dict):
        # common key names that may contain job/task id
        for jobkey in ("taskId", "task_id", "job_id", "jobId", "id"):
            if data.get("data") and isinstance(data.get("data"), dict) and data["data"].get(jobkey):
                raise HailuoError(f"API returned async task id. You must poll the provider. Received: {data}")

    # If we reached here, we don't know how to extract the video — return full JSON for debugging
    raise HailuoError(f"Unexpected response format from Hailuo API: {data}")

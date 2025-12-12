# hailuo_api.py
import os
import requests
import json
from typing import Optional

class HailuoError(Exception):
    pass

ENDPOINT = os.getenv("HAILUO_ENDPOINT", "https://modelslab.com/api/v7/video-fusion/text-to-video")
DEFAULT_MODEL_ID = os.getenv("HAILUO_MODEL", "hailuo-text-to-video")  # override via env

def _fetch_url(url: str, timeout: int = 60) -> bytes:
    r = requests.get(url, timeout=timeout, stream=True)
    if r.status_code != 200:
        raise HailuoError(f"Failed to fetch URL {url}: HTTP {r.status_code}")
    return r.content

def generate_hailuo_video(prompt: str, duration: int = 6, size: str = "720x1280", timeout: int = 120) -> bytes:
    """
    Call ModelsLab text->video endpoint and return raw video bytes.
    - Requires env var HAILUO_API_KEY (name below). (See bot.py usage)
    - Optional env var HAILUO_MODEL to override model_id.
    - duration in seconds (default 6)
    - size like "720x1280" (height x width) depending on API contract
    """
    api_key = os.getenv("HAILUO_API_KEY") or os.getenv("NANO_BANANA_API_KEY")
    if not api_key:
        raise HailuoError("Missing HAILUO_API_KEY environment variable")

    model_id = os.getenv("HAILUO_MODEL", DEFAULT_MODEL_ID)
    if not model_id:
        raise HailuoError("Missing model id: set HAILUO_MODEL environment variable")

    payload = {
        "key": api_key,
        "model_id": model_id,
        "prompt": prompt,
        # endpoint might accept additional options — keep sensible defaults
        "duration": duration,
        "size": size
    }

    headers = {"Content-Type": "application/json"}
    resp = requests.post(ENDPOINT, json=payload, headers=headers, timeout=timeout)

    if resp.status_code != 200:
        try:
            data = resp.json()
            raise HailuoError(f"API error: {data}")
        except Exception:
            raise HailuoError(f"HTTP error {resp.status_code}: {resp.text[:500]}")

    # Parse JSON response
    try:
        data = resp.json()
    except Exception:
        # maybe the endpoint returned raw bytes (unlikely). fallback:
        content_type = resp.headers.get("Content-Type", "")
        if content_type.startswith("video/") or content_type.startswith("application/octet-stream"):
            return resp.content
        raise HailuoError("Unexpected non-JSON response from Hailuo API")

    # Common ModelsLab response shapes:
    # - "output": ["https://.../result.mp4"]
    # - "proxy_links": [...]
    # - "video" : { "url": "..." } or "videos":[ "url" ]
    # - or data.results etc.

    # 1) output / proxy_links top-level lists
    for list_key in ("output", "proxy_links", "outputs", "proxyLinks"):
        arr = data.get(list_key) if isinstance(data, dict) else None
        if isinstance(arr, list) and len(arr) > 0 and isinstance(arr[0], str) and arr[0].startswith("http"):
            return _fetch_url(arr[0])

    # 2) video fields
    if isinstance(data, dict):
        # video: { "url": "..." }
        v = data.get("video") or data.get("result") or data.get("output_video")
        if isinstance(v, dict) and isinstance(v.get("url"), str):
            return _fetch_url(v["url"])
        if isinstance(v, list) and len(v) > 0 and isinstance(v[0], str) and v[0].startswith("http"):
            return _fetch_url(v[0])

    # 3) nested arrays like data["data"][0]["url"] or data["data"][0]["video_url"]
    for arr_key in ("data", "results", "artifacts"):
        arr = data.get(arr_key) if isinstance(data, dict) else None
        if isinstance(arr, list) and len(arr) > 0:
            first = arr[0]
            if isinstance(first, dict):
                for k in ("url", "video_url", "output", "result"):
                    if k in first and isinstance(first[k], str) and first[k].startswith("http"):
                        return _fetch_url(first[k])
            elif isinstance(first, str) and first.startswith("http"):
                return _fetch_url(first)

    # Nothing found
    raise HailuoError(f"Unexpected response format from Hailuo API: {json.dumps(data)[:1000]}")

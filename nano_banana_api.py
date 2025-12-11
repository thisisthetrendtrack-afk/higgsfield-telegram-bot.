# nano_banana_api.py
import os
import requests
import base64
from typing import Optional

class NanoBananaError(Exception):
    pass

ENDPOINT = os.getenv("NANO_BANANA_ENDPOINT", "https://modelslab.com/api/v7/images/text-to-image")
DEFAULT_MODEL_ID = os.getenv("NANO_BANANA_MODEL", "nano-banana-pro")

def _try_decode_b64(s: str) -> Optional[bytes]:
    try:
        return base64.b64decode(s)
    except Exception:
        return None

def _fetch_url(url: str, timeout: int = 30) -> bytes:
    r = requests.get(url, timeout=timeout)
    if r.status_code != 200:
        raise NanoBananaError(f"Failed to fetch image URL {url}: HTTP {r.status_code}")
    return r.content

def generate_nano_image(prompt: str, size: str = "1024x1024", timeout: int = 60) -> bytes:
    api_key = os.getenv("NANO_BANANA_API_KEY")
    if not api_key:
        raise NanoBananaError("Missing NANO_BANANA_API_KEY environment variable")

    model_id = os.getenv("NANO_BANANA_MODEL", DEFAULT_MODEL_ID)
    if not model_id:
        raise NanoBananaError("Missing model id: set NANO_BANANA_MODEL environment variable")

    payload = {
        "key": api_key,
        "model_id": model_id,
        "prompt": prompt,
        "size": size
    }

    headers = {"Content-Type": "application/json"}
    resp = requests.post(ENDPOINT, json=payload, headers=headers, timeout=timeout)

    if resp.status_code != 200:
        try:
            err = resp.json()
            raise NanoBananaError(f"API error: {err}")
        except ValueError:
            raise NanoBananaError(f"HTTP error {resp.status_code}: {resp.text}")

    # parse JSON
    try:
        data = resp.json()
    except ValueError:
        content_type = resp.headers.get("Content-Type", "")
        if content_type.startswith("image/"):
            return resp.content
        raise NanoBananaError("Unexpected non-JSON response from API")

    # 1) base64 in images[]
    if isinstance(data, dict) and "images" in data and isinstance(data["images"], list) and len(data["images"]) > 0:
        first = data["images"][0]
        if isinstance(first, str):
            dec = _try_decode_b64(first)
            if dec:
                return dec
            if first.startswith("http"):
                return _fetch_url(first)
        elif isinstance(first, dict):
            for k in ("b64", "b64_json", "base64", "image_base64"):
                if k in first and isinstance(first[k], str):
                    dec = _try_decode_b64(first[k])
                    if dec:
                        return dec
            url = first.get("url") or first.get("image_url")
            if url:
                return _fetch_url(url)

    # 2) data / outputs arrays (common shapes)
    for arr_key in ("data", "outputs", "artifacts", "result", "results", "output"):
        arr = data.get(arr_key) if isinstance(data, dict) else None
        if isinstance(arr, list) and len(arr) > 0:
            first = arr[0]
            if isinstance(first, str):
                # could be base64 or URL
                dec = _try_decode_b64(first)
                if dec:
                    return dec
                if first.startswith("http"):
                    return _fetch_url(first)
            elif isinstance(first, dict):
                for k in ("b64_json", "b64", "base64", "image_base64"):
                    if k in first and isinstance(first[k], str):
                        dec = _try_decode_b64(first[k])
                        if dec:
                            return dec
                url = first.get("url") or first.get("image_url")
                if url:
                    return _fetch_url(url)

    # 3) direct 'output' or 'proxy_links' top-level lists (ModelsLab uses 'output' in your screenshot)
    for list_key in ("output", "proxy_links", "proxyLinks"):
        arr = data.get(list_key) if isinstance(data, dict) else None
        if isinstance(arr, list) and len(arr) > 0:
            first = arr[0]
            if isinstance(first, str) and first.startswith("http"):
                return _fetch_url(first)

    # 4) top-level URL fields
    for k in ("url", "image_url", "output_url", "result", "file"):
        v = data.get(k) if isinstance(data, dict) else None
        if isinstance(v, str) and v.startswith("http"):
            return _fetch_url(v)

    # If nothing found, raise helpful error (include snippet)
    raise NanoBananaError(f"Unexpected response: {data}")

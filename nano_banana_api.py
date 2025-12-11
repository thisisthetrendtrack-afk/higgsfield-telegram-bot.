# nano_banana_api.py (replace existing function with this)
import os
import requests
import base64
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nano_banana_api")

class NanoBananaError(Exception):
    pass

MODELSLAB_ENDPOINT = os.getenv("NANO_BANANA_ENDPOINT", "https://modelslab.com/api/v7/images/text-to-image")
DEFAULT_MODEL = os.getenv("NANO_BANANA_MODEL", "nano-banana-pro")

def _dump_response(resp):
    # Save response body for inspection
    try:
        body = resp.text
        path = "/tmp/nano_last_response.json"
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        logger.info(f"Wrote API response to {path}")
    except Exception as e:
        logger.exception("Failed to dump response: %s", e)

def _safe_get(dct, *keys):
    """Utility to walk nested dicts safely."""
    cur = dct
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
        if cur is None:
            return None
    return cur

def _try_extract_image_from_json(data):
    # Try many common shapes and keys
    # 1) top-level base64-like keys
    for key in ("image_base64", "imageB64", "base64", "b64"):
        v = data.get(key) if isinstance(data, dict) else None
        if isinstance(v, str) and len(v) > 100:
            return base64.b64decode(v)

    # 2) data: [ { b64_json / b64 / url } ]
    for arr_key in ("data", "images", "outputs", "artifacts", "result", "results"):
        arr = data.get(arr_key) if isinstance(data, dict) else None
        if isinstance(arr, list) and len(arr) > 0:
            first = arr[0]
            if isinstance(first, dict):
                # base64 variants
                for k in ("b64_json", "b64", "base64", "image_base64"):
                    if k in first and isinstance(first[k], str) and len(first[k]) > 100:
                        return base64.b64decode(first[k])
                # url variants
                for k in ("url", "image_url", "src", "href"):
                    if k in first and isinstance(first[k], str) and first[k].startswith("http"):
                        r2 = requests.get(first[k], timeout=30)
                        if r2.status_code == 200:
                            return r2.content
            # sometimes list contains direct url strings
            if isinstance(arr[0], str) and arr[0].startswith("http"):
                r2 = requests.get(arr[0], timeout=30)
                if r2.status_code == 200:
                    return r2.content

    # 3) top-level url fields
    for key in ("url", "image_url", "output", "output_url", "result", "file"):
        v = data.get(key) if isinstance(data, dict) else None
        if isinstance(v, str) and v.startswith("http"):
            r2 = requests.get(v, timeout=30)
            if r2.status_code == 200:
                return r2.content

    return None

def generate_nano_image(prompt: str, size: str = "1024x1024", timeout: int = 60) -> bytes:
    api_key = os.getenv("NANO_BANANA_API_KEY")
    if not api_key:
        raise NanoBananaError("Missing NANO_BANANA_API_KEY environment variable")

    payload = {
        "model": os.getenv("NANO_BANANA_MODEL", DEFAULT_MODEL),
        "prompt": prompt,
        "size": size
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    resp = requests.post(MODELSLAB_ENDPOINT, json=payload, headers=headers, timeout=timeout)
    # save response for debugging
    try:
        _dump_response(resp)
    except:
        pass

    # surface helpful errors early
    content_type = resp.headers.get("Content-Type", "")
    if resp.status_code >= 400:
        # try parse json error
        try:
            err = resp.json()
            # if provider returns structured error
            if isinstance(err, dict) and ("error" in err or "message" in err):
                raise NanoBananaError(f"HTTP {resp.status_code}: {err}")
            else:
                raise NanoBananaError(f"HTTP {resp.status_code}: {err}")
        except ValueError:
            raise NanoBananaError(f"HTTP {resp.status_code}: {resp.text[:500]}")

    # If direct image bytes returned
    if content_type.startswith("image/"):
        return resp.content

    # Try parse JSON
    try:
        data = resp.json()
    except ValueError:
        # Not JSON, fallback
        raise NanoBananaError(f"Unexpected non-JSON response (content-type={content_type}): {resp.text[:500]}")

    # If JSON contains explicit error info
    if isinstance(data, dict) and ("error" in data or "message" in data):
        # prefer structured error
        err_msg = data.get("error") or data.get("message") or str(data)
        raise NanoBananaError(f"API returned error: {err_msg}")

    # Try to extract image from JSON
    image_bytes = _try_extract_image_from_json(data)
    if image_bytes:
        return image_bytes

    # Nothing found — include helpful debug snippet in error
    short = json.dumps(data)[:1000]
    raise NanoBananaError(f"Unexpected API response – no image found. Response snippet: {short}")

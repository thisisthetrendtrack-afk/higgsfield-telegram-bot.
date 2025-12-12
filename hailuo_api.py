# hailuo_api.py (FIXED POST FETCH)
import os
import time
import logging
import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")
HAILUO_MODEL = os.getenv("HAILUO_MODEL")
ENDPOINT = "https://modelslab.com/api/v7/video-fusion/text-to-video"

class HailuoError(Exception):
    pass

def _download(url: str) -> bytes:
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content

def _pick_link(data):
    for key in ("future_links", "output", "result", "video_url", "url"):
        val = data.get(key)
        if isinstance(val, list) and val and isinstance(val[0], str):
            return val[0]
        if isinstance(val, str) and val.startswith("http"):
            return val
    return None

def generate_hailuo_video(prompt, duration="6", size="720x1280"):
    if not MODELSLAB_KEY:
        raise HailuoError("Missing MODELSLAB_KEY")

    if not HAILUO_MODEL:
        raise HailuoError("Missing HAILUO_MODEL")

    payload = {
        "key": MODELSLAB_KEY,
        "model_id": HAILUO_MODEL,
        "prompt": prompt,
        "duration": str(duration),
        "size": size
    }

    # ---- STEP 1: submit job ----
    resp = requests.post(ENDPOINT, json=payload, timeout=60)
    data = resp.json()

    # immediate success
    if data.get("status") == "success":
        link = _pick_link(data)
        if not link:
            raise HailuoError(f"No video link found: {data}")
        return _download(link)

    # ---- STEP 2: processing → poll fetch_result ----
    if data.get("status") == "processing":
        fetch_url = data.get("fetch_result")
        if not fetch_url:
            raise HailuoError(f"No fetch_result URL provided: {data}")

        # wait ETA before polling
        time.sleep(int(data.get("eta", 5)))

        # start polling
        for i in range(80):  # ~4–5 minutes
            poll_payload = {"key": MODELSLAB_KEY}
            r = requests.post(fetch_url, json=poll_payload, timeout=60)
            j = r.json()

            # if error returned
            if j.get("status") == "error":
                raise HailuoError(f"Hailuo fetch returned error: {j}")

            # when done
            if j.get("status") == "success":
                link = _pick_link(j)
                if not link:
                    raise HailuoError(f"No final link found: {j}")
                return _download(link)

            time.sleep(3)

        raise HailuoError("Timeout waiting for final video")

    raise HailuoError(f"Unexpected response: {data}")

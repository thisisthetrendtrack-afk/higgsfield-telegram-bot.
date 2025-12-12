# hailuo_api.py
import os
import time
import requests

MODELSLAB_KEY = os.getenv("MODELSLAB_KEY")
HAILUO_MODEL = os.getenv("HAILUO_MODEL")
ENDPOINT = "https://modelslab.com/api/v7/video-fusion/text-to-video"

class HailuoError(Exception):
    pass

def generate_hailuo_video(prompt, duration="6", size="720x1280", timeout=600):
    if not MODELSLAB_KEY:
        raise HailuoError("MODELSLAB_KEY not set")

    if not HAILUO_MODEL:
        raise HailuoError("HAILUO_MODEL not set (model_id)")

    payload = {
        "key": MODELSLAB_KEY,
        "model_id": HAILUO_MODEL,
        "prompt": prompt,
        "duration": str(duration),
        "size": size
    }

    # First request
    resp = requests.post(ENDPOINT, json=payload, timeout=60)
    data = resp.json()

    # If model is processing, we must poll
    if data.get("status") == "processing":
        fetch_url = data.get("fetch_result")
        eta = data.get("eta", 10)

        # Wait a bit before polling
        time.sleep(int(eta))

        # Poll until ready
        for _ in range(40):  # ~40 retries = ~5 minutes
            r = requests.get(fetch_url, timeout=30)
            j = r.json()

            # Success
            if j.get("status") == "success":
                # Extract video URL
                link = None

                # 1) future_links
                if j.get("future_links"):
                    link = j["future_links"][0]

                # fallback: output, video_url
                if not link:
                    for key in ("output", "video_url", "result", "url"):
                        if j.get(key):
                            if isinstance(j[key], list):
                                link = j[key][0]
                            else:
                                link = j[key]
                            break

                if not link:
                    raise HailuoError(f"Could not find video URL in: {j}")

                # Download video bytes
                vid = requests.get(link, timeout=60)
                return vid.content

            # If still processing
            time.sleep(3)

        raise HailuoError("Timeout waiting for Hailuo video")

    # If immediate success (rare)
    if data.get("status") == "success":
        link = data.get("output") or data.get("video_url")
        if isinstance(link, list):
            link = link[0]
        vid = requests.get(link, timeout=60)
        return vid.content

    raise HailuoError(f"Unexpected response: {data}")

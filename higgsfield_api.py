import os
import requests

API_KEY = os.getenv("HIGGSFIELD_API_KEY")
BASE = "https://api.higgsfield.ai/v1"

def create_dop_job(image_url, prompt):
    if not API_KEY:
        raise RuntimeError("HIGGSFIELD_API_KEY not set")

    payload = {
        "model": "dop-turbo",
        "image_url": image_url,
        "prompt": prompt,
        "enhance_prompt": True
    }

    r = requests.post(
        f"{BASE}/image2video/dop",
        json=payload,
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    r.raise_for_status()

    return r.json()["job_set_id"]

def poll_job_status(job_set_id):
    if not API_KEY:
        raise RuntimeError("HIGGSFIELD_API_KEY not set")

    r = requests.get(
        f"{BASE}/job-sets/{job_set_id}",
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    r.raise_for_status()

    data = r.json()
    status = data["status"]

    if status == "completed":
        return status, data["results"]["raw"]["url"]

    return status, None

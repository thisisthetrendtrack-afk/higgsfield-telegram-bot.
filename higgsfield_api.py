import os
import httpx
import base64
import asyncioimport base64
import httpx

class HiggsfieldAPI:
    def __init__(self, hf_key: str, hf_secret: str):
        self.base_url = "https://api.higgsfield.ai"
        self.hf_key = hf_key
        self.hf_secret = hf_secret

    def _auth_headers(self):
        token = f"{self.hf_key}:{self.hf_secret}"
        encoded = base64.b64encode(token.encode()).decode()
        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json"
        }

    # -------------------------
    # DoP IMAGE → VIDEO
    # -------------------------
    async def dop(self, image_url: str, prompt: str):
        url = f"{self.base_url}/v1/image2video/dop"
        payload = {
            "image_url": image_url,
            "prompt": prompt,
            "model": "dop-turbo",
            "enhance_prompt": True
        }

        async with httpx.AsyncClient(timeout=200) as client:
            r = await client.post(url, json=payload, headers=self._auth_headers())
            r.raise_for_status()
            res = r.json()

        job_id = res.get("job_set_id") or res.get("id")
        return job_id, res

    # -------------------------
    # TEXT → IMAGE
    # -------------------------
    async def txt2img(self, prompt: str):
        url = f"{self.base_url}/v1/text2image"
        payload = {
            "prompt": prompt,
            "model": "higgs-turbo",
            "enhance_prompt": True
        }

        async with httpx.AsyncClient(timeout=200) as client:
            r = await client.post(url, json=payload, headers=self._auth_headers())
            r.raise_for_status()
            res = r.json()

        job_id = res.get("job_set_id") or res.get("id")
        return job_id, res

    # -------------------------
    # STYLE IMAGE
    # -------------------------
    async def stylize(self, image_url: str, style: str):
        url = f"{self.base_url}/v1/image/stylize"
        payload = {
            "image_url": image_url,
            "style": style
        }

        async with httpx.AsyncClient(timeout=200) as client:
            r = await client.post(url, json=payload, headers=self._auth_headers())
            r.raise_for_status()
            res = r.json()

        job_id = res.get("job_set_id") or res.get("id")
        return job_id, res

    # -------------------------
    # TEXT → VIDEO (motions)
    # -------------------------
    async def txt2video(self, prompt: str):
        url = f"{self.base_url}/v1/text2video"
        payload = {
            "prompt": prompt,
            "model": "higgs-video",
            "enhance_prompt": True
        }

        async with httpx.AsyncClient(timeout=200) as client:
            r = await client.post(url, json=payload, headers=self._auth_headers())
            r.raise_for_status()
            res = r.json()

        job_id = res.get("job_set_id") or res.get("id")
        return job_id, res

    # -------------------------
    # JOB STATUS
    # -------------------------
    async def get_status(self, job_id: str):
        url = f"{self.base_url}/v1/job-sets/{job_id}"

        async with httpx.AsyncClient(timeout=200) as client:
            r = await client.get(url, headers=self._auth_headers())
            r.raise_for_status()
            return r.json()

HF_KEY = os.getenv("HF_KEY")
HF_SECRET = os.getenv("HF_SECRET")

BASE_URL = "https://api.higgsfield.ai/v1"

headers = {
    "HF-Api-Key": HF_KEY,
    "HF-Api-Secret": HF_SECRET,
    "Content-Type": "application/json"
}

async def txt2img(prompt: str):
    url = f"{BASE_URL}/text2image"

    payload = {
        "prompt": prompt,
        "model": "prodia",
        "enhance_prompt": True
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json()
        return data.get("job_set_id")

async def image2image(image_path, prompt):
    url = f"{BASE_URL}/image2image"

    with open(image_path, "rb") as f:
        b64img = base64.b64encode(f.read()).decode()

    payload = {
        "image": b64img,
        "prompt": prompt,
        "model": "controlnet"
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json().get("job_set_id")

async def dop_video(image_path, prompt):
    url = f"{BASE_URL}/image2video/dop"

    with open(image_path, "rb") as f:
        b64img = base64.b64encode(f.read()).decode()

    payload = {
        "image": b64img,
        "prompt": prompt,
        "model": "dop-turbo",
        "enhance_prompt": True
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json().get("job_set_id")

async def check_status(job_id):
    url = f"{BASE_URL}/job-sets/{job_id}"

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()

        status = data.get("status")
        outputs = data.get("output", [])

        video_url = None
        image_url = None

        if outputs:
            out = outputs[0]
            video_url = out.get("video_url")
            image_url = out.get("image_url")

        return status, video_url, image_url

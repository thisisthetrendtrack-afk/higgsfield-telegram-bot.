import base64
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

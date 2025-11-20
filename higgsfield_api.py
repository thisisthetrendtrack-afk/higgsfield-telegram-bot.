import base64
import aiohttp
import asyncio


class HiggsfieldAPI:

    def __init__(self, key: str, secret: str):
        self.base = "https://api.higgsfield.ai/v1"
        self.key = key
        self.secret = secret
        self.headers = {
            "Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode(),
            "Content-Type": "application/json"
        }

    # ----------------------------------------------------
    # INTERNAL POST
    # ----------------------------------------------------
    async def _post(self, endpoint, payload):
        url = f"{self.base}/{endpoint}"

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=self.headers) as res:
                if res.status >= 300:
                    raise Exception(f"API Error {res.status}: {await res.text()}")
                return await res.json()

    # ----------------------------------------------------
    # INTERNAL GET
    # ----------------------------------------------------
    async def _get(self, endpoint):
        url = f"{self.base}/{endpoint}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as res:
                if res.status >= 300:
                    raise Exception(f"API Error {res.status}: {await res.text()}")
                return await res.json()

    # ----------------------------------------------------
    # DoP Image → Video
    # ----------------------------------------------------
    async def create_dop_job(self, image_path: str, prompt: str):
        payload = {
            "image_url": image_path,
            "prompt": prompt,
            "model": "dop-turbo",
            "enhance_prompt": True
        }

        data = await self._post("image2video/dop", payload)

        job_id = (
            data.get("job_set_id")
            or data.get("jobSetId")
            or data.get("id")
            or data.get("job_set")
        )

        return job_id, data

    # ----------------------------------------------------
    # TEXT → IMAGE
    # ----------------------------------------------------
    async def txt2img(self, prompt: str):
        payload = {
            "prompt": prompt,
            "model": "txt2img-turbo"
        }

        data = await self._post("txt2img", payload)

        job_id = data.get("job_set_id") or data.get("id")
        return job_id, data

    # ----------------------------------------------------
    # TEXT → VIDEO
    # ----------------------------------------------------
    async def txt2video(self, prompt: str):
        payload = {
            "prompt": prompt,
            "model": "txt2video-turbo"
        }

        data = await self._post("txt2video", payload)

        job_id = data.get("job_set_id") or data.get("id")
        return job_id, data

    # ----------------------------------------------------
    # STYLIZE IMAGE
    # ----------------------------------------------------
    async def stylize(self, image_path: str, prompt: str = None):
        payload = {
            "image_url": image_path,
            "prompt": prompt,
            "model": "image-style"
        }

        data = await self._post("image-style", payload)

        job_id = data.get("job_set_id") or data.get("id")
        return job_id, data

    # ----------------------------------------------------
    # JOB STATUS CHECK
    # ----------------------------------------------------
    async def get_job_status(self, job_id: str):
        return await self._get(f"job-sets/{job_id}")

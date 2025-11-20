import base64
import requests


class HiggsfieldAPI:
    def __init__(self, hf_key, hf_secret):
        self.key = hf_key
        self.secret = hf_secret
        self.url = "https://api.higgsfield.ai"

    def _auth(self):
        token = base64.b64encode(f"{self.key}:{self.secret}".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def _post(self, endpoint, json):
        return requests.post(
            f"{self.url}{endpoint}",
            headers=self._auth(),
            json=json,
            timeout=120,
        ).json()

    def _get(self, endpoint):
        return requests.get(
            f"{self.url}{endpoint}",
            headers=self._auth(),
            timeout=120,
        ).json()

    # --------------------
    # ALL HIGGS OPTIONS
    # --------------------
    def dop(self, file, prompt):
        return self._post("/v1/image2video/dop", {
            "image_url": file,
            "prompt": prompt,
            "model": "dop-turbo",
            "enhance_prompt": True
        })

    def popcorn(self, file, prompt):
        return self._post("/v1/image2video/popcorn", {
            "image_url": file,
            "prompt": prompt
        })

    def face_animate(self, file):
        return self._post("/v1/face/animate", {
            "image_url": file
        })

    def face_to_video(self, file, prompt):
        return self._post("/v1/face/2video", {
            "image_url": file,
            "prompt": prompt
        })

    def extend_video(self, file, prompt):
        return self._post("/v1/video/extend", {
            "video_url": file,
            "prompt": prompt
        })

    def stylize(self, file, prompt):
        return self._post("/v1/image/stylize", {
            "image_url": file,
            "style_prompt": prompt
        })

    def text_to_image(self, prompt):
        return self._post("/v1/text2image", {"prompt": prompt})

    def text_to_video(self, prompt):
        return self._post("/v1/text2video", {"prompt": prompt})

    def job_status(self, job_id):
        return self._get(f"/v1/job-sets/{job_id}")

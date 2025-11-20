import os
import asyncio
import base64
import requests


class HiggsfieldAPI:
    def __init__(self, key, secret):
        self.key = key
        self.secret = secret
        self.base = "https://cloud.higgsfield.ai/v1"

        self.headers = {
            "x-api-key": self.key,
            "x-api-secret": self.secret,
            "Content-Type": "application/json"
        }

    # -----------------------------------------------------------
    # DoP IMAGE → VIDEO
    # -----------------------------------------------------------
    def create_dop_job(self, image_url, prompt):
        url = f"{self.base}/image2video/dop"

        payload = {
            "model": "dop",
            "enhance_prompt": True,
            "image": image_url,
            "prompt": prompt
        }

        try:
            r = requests.post(url, json=payload, headers=self.headers)
            data = r.json()

            jobset_id = data.get("job_set_id")
            return jobset_id, data

        except Exception as e:
            return None, {"error": str(e)}

    # -----------------------------------------------------------
    # GET JOB STATUS
    # -----------------------------------------------------------
    def get_job_status(self, job_set_id):
        url = f"{self.base}/job-sets/{job_set_id}"

        r = requests.get(url, headers=self.headers)
        return r.json()

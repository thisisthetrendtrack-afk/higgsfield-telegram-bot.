# nano_banana_api.py

import requests
import json
import os
import base64


class NanoBananaAPI:
    """
    API Wrapper for Nano Banana Pro model.
    Endpoints:
      - POST /createTask
      - GET /recordInfo
    """

    BASE_URL = "https://api.kie.ai/api/v1/jobs"

    def __init__(self, api_key=None):
        # Read API key from environment variable
        self.api_key = api_key or os.getenv("NANO_BANANA_API_KEY")

        if not self.api_key:
            raise Exception(
                "Missing API Key! Set NANO_BANANA_API_KEY in Railway Variables."
            )

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    # ---------------------------------------------------
    # CREATE GENERATION TASK
    # ---------------------------------------------------
    def create_task(
        self,
        prompt: str,
        image_bytes: bytes | None = None,
        aspect_ratio: str = "1:1",
        resolution: str = "1K",
        output_format: str = "png",
        callback_url: str | None = None
    ):
        """
        Creates a Nano Banana Pro generation job.
        """

        payload = {
            "model": "nano-banana-pro",
            "input": {
                "prompt": prompt,
                "image_input": [],
                "aspect_ratio": aspect_ratio,
                "resolution": resolution,
                "output_format": output_format
            }
        }

        # Add callback URL if user wants it
        if callback_url:
            payload["callBackUrl"] = callback_url

        # If using image → convert to base64
        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode("utf-8")
            payload["input"]["image_input"] = [b64]

        response = requests.post(
            f"{self.BASE_URL}/createTask",
            headers=self.headers,
            data=json.dumps(payload)
        )

        return response.json()

    # ---------------------------------------------------
    # QUERY TASK STATUS
    # ---------------------------------------------------
    def check_task(self, task_id: str):
        """
        Polls job status by taskId.
        """

        response = requests.get(
            f"{self.BASE_URL}/recordInfo",
            headers={"Authorization": f"Bearer {self.api_key}"},
            params={"taskId": task_id}
        )

        return response.json()

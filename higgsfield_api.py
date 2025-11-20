import requests
import time


class HiggsfieldAPI:
    BASE_URL = "https://platform.higgsfield.ai"

    def __init__(self, key: str, secret: str):
        self.key = key
        self.secret = secret
        self.headers = {
            "Authorization": f"Key {self.key}:{self.secret}",
            "Content-Type": "application/json"
        }

    # --------------------------
    # SUBMIT A GENERATION JOB
    # --------------------------
    def submit(self, model_id: str, payload: dict) -> dict:
        """
        Example model_id: "higgsfield-ai/soul/standard"
        """
        url = f"{self.BASE_URL}/{model_id}"
        resp = requests.post(url, headers=self.headers, json=payload)
        resp.raise_for_status()
        return resp.json()

    # --------------------------
    # GET STATUS OF A JOB
    # --------------------------
    def get_status(self, request_id: str) -> dict:
        url = f"{self.BASE_URL}/requests/{request_id}/status"
        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    # --------------------------
    # WAIT UNTIL JOB FINISHES
    # --------------------------
    def wait_for_result(self, request_id: str, interval=4, timeout=300):
        elapsed = 0
        while elapsed < timeout:
            data = self.get_status(request_id)
            status = data.get("status")

            if status in ["completed", "failed", "nsfw"]:
                return data

            time.sleep(interval)
            elapsed += interval

        return {"status": "timeout", "request_id": request_id}

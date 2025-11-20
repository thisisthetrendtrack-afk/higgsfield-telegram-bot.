import os
import time
import uuid
import requests


BASE_URL = "https://platform.higgsfield.ai"


class HiggsfieldAPI:
    def __init__(self, key, secret):
        self.key = key
        self.secret = secret
        self.headers = {
            "Authorization": f"Key {self.key}:{self.secret}",
            "Content-Type": "application/json"
        }

    # -----------------------------
    # SUBMIT GENERATION REQUEST
    # -----------------------------
    def submit(self, model_id, payload):
        url = f"{BASE_URL}/{model_id}"

        print("Submitting to:", url)
        print("Payload:", payload)

        resp = requests.post(url, headers=self.headers, json=payload)

        if resp.status_code != 200:
            raise RuntimeError(f"API error: {resp.status_code} {resp.text}")

        data = resp.json()
        return data  # contains request_id + status_url

    # -----------------------------
    # POLL STATUS
    # -----------------------------
    def get_status(self, request_id):
        url = f"{BASE_URL}/requests/{request_id}/status"

        resp = requests.get(url, headers=self.headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Status error: {resp.status_code}")

        return resp.json()

    # -----------------------------
    # WAIT UNTIL COMPLETED
    # -----------------------------
    def wait_for_result(self, request_id, delay=5):
        while True:
            data = self.get_status(request_id)

            status = data.get("status")

            print("Status:", status)

            if status in ["completed", "failed", "nsfw"]:
                return data

            time.sleep(delay)

import os
import asyncio
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

    # SUBMIT REQUEST
    def submit(self, model_id, payload):
        url = f"{BASE_URL}/{model_id}"
        print(f"🚀 Submitting to {url}...")
        resp = requests.post(url, headers=self.headers, json=payload)
        
        if resp.status_code != 200:
            raise RuntimeError(f"API error: {resp.status_code} {resp.text}")
        
        return resp.json()

    # GET STATUS
    def get_status(self, request_id):
        url = f"{BASE_URL}/requests/{request_id}/status"
        resp = requests.get(url, headers=self.headers)
        
        if resp.status_code != 200:
            raise RuntimeError(f"Status error: {resp.status_code} {resp.text}")
        
        return resp.json()

    # WAIT FOR RESULT (ASYNC)
    async def wait_for_result(self, request_id, delay=4):
        print(f"⏳ Waiting for task {request_id}...")
        while True:
            # Run the blocking request in a separate thread
            data = await asyncio.to_thread(self.get_status, request_id)
            status = data.get("status")

            if status in ["completed", "failed", "nsfw"]:
                return data

            await asyncio.sleep(delay)

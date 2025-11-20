    async def txt2img(self, prompt: str):
        url = f"{self.base_url}/v1/text2image"
        payload = {
            "prompt": prompt,
            "model": "higgs-turbo",
            "enhance_prompt": True
        }

        headers = {"Content-Type": "application/json"}
        headers.update(self._auth_headers())

        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()

        job_set_id = data.get("job_set_id") or data.get("id")
        return job_set_id, data

"""
Wrapper for the Higgsfield API.

This module defines a small helper class used by the bot to interact with
Higgsfield's HTTP endpoints. Only the minimal set of functionality
required for the DoP image‑to‑video workflow is implemented. The class
exposes two methods:

* ``create_dop_job`` – create a new DoP job from an image URL and text
  prompt. Returns the job set identifier assigned by the API.
* ``get_job_status`` – retrieve the status of a previously created job
  given its job set identifier. Returns the raw JSON response.

The actual structure of the responses is not publicly documented at
the time of writing, so the methods avoid strict schema enforcement
and instead return the raw data to be interpreted by the callers.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Dict, Optional, Tuple

import requests


class HiggsfieldAPI:
    """Simple synchronous wrapper around the Higgsfield REST API."""

    def __init__(self, hf_key: Optional[str] = None, hf_secret: Optional[str] = None) -> None:
        """Create a new API client.

        Args:
            hf_key: Your Higgsfield API key. Optional if your endpoints do not
                require authentication (for example, when testing locally).
            hf_secret: Your Higgsfield API secret. Optional but required for
                authenticated requests.
        """
        self.base_url = "https://api.higgsfield.ai"
        self.hf_key = hf_key
        self.hf_secret = hf_secret

    def _auth_headers(self) -> Dict[str, str]:
        """Construct HTTP headers for authenticated requests.

        The Higgsfield API uses a key and secret for authentication. If both
        credentials are provided this method returns a dictionary with
        ``Authorization`` header using basic authentication. If either
        credential is missing the returned dictionary is empty.

        Returns:
            A dictionary of headers to include in authenticated requests.
        """
        if self.hf_key and self.hf_secret:
            # Basic authentication expects a base64 encoded 'key:secret' string.
            token = f"{self.hf_key}:{self.hf_secret}"
            encoded = base64.b64encode(token.encode()).decode()
            return {"Authorization": f"Basic {encoded}"}
        return {}

    def create_dop_job(self, image_url: str, prompt: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """Create a new DoP job.

        Sends a POST request to the ``/v1/image2video/dop`` endpoint with the
        supplied image URL and prompt. The payload includes the model
        selection and instructs the API to enhance the prompt. On success
        returns the job set identifier along with the raw JSON response.

        Args:
            image_url: Publicly reachable URL of the source image.
            prompt: Text prompt describing the desired motion in the video.

        Returns:
            A tuple ``(job_set_id, response_json)``. ``job_set_id`` may be
            ``None`` if the response does not contain it.

        Raises:
            requests.HTTPError: If the API returns a non‑2xx status code.
        """
        url = f"{self.base_url}/v1/image2video/dop"
        payload: Dict[str, Any] = {
            "image_url": image_url,
            "prompt": prompt,
            "model": "dop-turbo",
            "enhance_prompt": True,
        }
        headers = {"Content-Type": "application/json"}
        headers.update(self._auth_headers())

        response = requests.post(url, headers=headers, json=payload, timeout=120)
        # Raise an exception for bad HTTP status codes. The caller can catch
        # and handle it as appropriate.
        response.raise_for_status()
        data: Dict[str, Any] = response.json()
        # The response format is not guaranteed; attempt to extract job_set_id.
        job_set_id: Optional[str] = (
            data.get("job_set_id")
            or data.get("jobSetId")
            or data.get("job_set")
            or data.get("id")
        )
        return job_set_id, data

    def get_job_status(self, job_set_id: str) -> Dict[str, Any]:
        """Retrieve the status of a job.

        Queries the ``/v1/job-sets/{job_set_id}`` endpoint and returns the
        parsed JSON response. If the API responds with an error code this
        method will raise an exception.

        Args:
            job_set_id: Identifier returned when the job was created.

        Returns:
            The raw JSON response from the API.

        Raises:
            requests.HTTPError: If the API returns a non‑2xx status code.
        """
        url = f"{self.base_url}/v1/job-sets/{job_set_id}"
        headers = {}
        headers.update(self._auth_headers())
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        return response.json()
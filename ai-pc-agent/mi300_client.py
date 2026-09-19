"""HTTP client for the already-running MI300 semantic observation API."""

from __future__ import annotations

import base64
import os
from typing import Any

from observation_models import validate_semantic_memory


class MI300Client:
    def __init__(self, base_url: str | None = None, path: str | None = None, *, transport=None, timeout: float = 60):
        self.base_url = (base_url or os.getenv("MI300_API", "http://localhost:8000")).rstrip("/")
        self.path = path or os.getenv("MI300_OBSERVATION_PATH", "/observations")
        if transport is None:
            import requests

            transport = requests
        self.transport = transport
        self.timeout = timeout

    def submit_observation(self, observation: dict[str, Any], image_bytes: bytes) -> dict[str, Any]:
        payload = {
            "observation": observation,
            "image_b64": base64.b64encode(image_bytes).decode("ascii"),
        }
        response = self.transport.post(self.base_url + "/" + self.path.lstrip("/"), json=payload, timeout=self.timeout)
        if hasattr(response, "raise_for_status"):
            response.raise_for_status()
        result = response.json() if hasattr(response, "json") else response
        validate_semantic_memory(result)
        return result

"""呼叫 MI300 的三支 API。格式見 docs/api.html §③④⑥：
- submit_observation：截圖 + observation -> {"text", "error"}（寫進 memory 的 screen episode）
- reply：對話 prompt（OpenAI 相容 messages）-> {"expr", "text"}（轉成 SayCommand 送 ESP32）
- analyze_homework：作業照片 + 逐字稿 -> {"analysis", "reassurance", "chatgpt_prompt"}
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from observation_models import validate_screen_description

_DEFAULT_BASE_URL = "http://localhost:8000"


def _post(transport, url: str, payload: dict, timeout: float) -> Any:
    response = transport.post(url, json=payload, timeout=timeout)
    if hasattr(response, "raise_for_status"):
        response.raise_for_status()
    return response.json() if hasattr(response, "json") else response


class MI300Client:
    def __init__(
        self, base_url: str | None = None, path: str | None = None, *, transport=None, timeout: float = 60, trace=None
    ):
        self.base_url = (base_url or os.getenv("MI300_API", _DEFAULT_BASE_URL)).rstrip("/")
        self.path = path or os.getenv("MI300_OBSERVATION_PATH", "/v1/screen-observations")
        self.chat_path = os.getenv("MI300_CHAT_PATH", "/v1/chat/completions")
        self.homework_path = os.getenv("MI300_HOMEWORK_PATH", "/v1/homework-analyses")
        if transport is None:
            import requests

            transport = requests
        self.transport = transport
        self.timeout = timeout
        # trace 是 trace_log.TraceLog（可選）：給 debug dashboard 看「傳了什麼、收到
        # 什麼」，跟 memory/ 那套長期記憶無關。故意在驗證/拋例外之前就記錄，這樣
        # dashboard 也能看到格式不對的壞回應，方便排查。
        self.trace = trace

    def _url(self, path: str) -> str:
        return self.base_url + "/" + path.lstrip("/")

    def submit_observation(self, observation: dict[str, Any], image_bytes: bytes) -> dict[str, Any]:
        payload = {
            "observation": observation,
            "image_b64": base64.b64encode(image_bytes).decode("ascii"),
        }
        result = _post(self.transport, self._url(self.path), payload, self.timeout)
        if self.trace is not None:
            self.trace.add("screen_observation", {"observation": observation}, result, image_bytes=image_bytes)
        validate_screen_description(result)
        return result

    def reply(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """messages 是 OpenAI 格式（見 prompt.py:build_messages）。回傳 {"expr", "text"}。"""
        payload = {"messages": messages, "response_format": {"type": "json_object"}}
        result = _post(self.transport, self._url(self.chat_path), payload, self.timeout)
        content = result["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError:
            parsed = {"raw": content}
        if self.trace is not None:
            self.trace.add("chat_reply", {"messages": messages}, parsed)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("text"), str) or not parsed["text"].strip():
            raise ValueError("reply must contain a non-empty text field")
        return parsed

    def analyze_homework(self, image_bytes: bytes, transcript: str = "") -> dict[str, Any]:
        payload = {
            "image_b64": base64.b64encode(image_bytes).decode("ascii"),
            "transcript": transcript,
        }
        result = _post(self.transport, self._url(self.homework_path), payload, self.timeout)
        if self.trace is not None:
            self.trace.add("homework_analysis", {"transcript": transcript}, result, image_bytes=image_bytes)
        for field in ("analysis", "reassurance", "chatgpt_prompt"):
            if field not in result:
                raise ValueError(f"homework analysis missing field: {field}")
        return result

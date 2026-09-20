"""ESP32-CAM 的 HTTP client。作業拍照流程用（見 docs/api.html §②⑥）：
拍照當下只打一次 snapshot，不做連續錄影/串流拉取——連續預覽（給使用者看倒數畫面）
是前端的事，不在這支 client 的範圍內。
"""
from __future__ import annotations

import time

import config


def capture_snapshot(
    transport=None,
    base_url: str | None = None,
    timeout: float = 10,
    attempts: int = 3,
    retry_delay: float = 0.35,
) -> bytes:
    if transport is None:
        import requests

        transport = requests
    url = (base_url or config.ESP32_CAM_BASE_URL).rstrip("/") + "/api/v1/cam/snapshot"
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            response = transport.get(url, timeout=timeout)
            if hasattr(response, "raise_for_status"):
                response.raise_for_status()
            return response.content if hasattr(response, "content") else response
        except Exception as exc:  # noqa: BLE001 — the stream may still be releasing its client
            last_error = exc
            if attempt + 1 < max(1, attempts):
                time.sleep(retry_delay)
    assert last_error is not None
    raise last_error

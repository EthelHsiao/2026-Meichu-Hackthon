"""Contract builders and validators shared by the local agent and MI300 client."""

from __future__ import annotations

from typing import Any, Mapping
from uuid import uuid4


_ENRICHMENT_NAMES = ("git", "vscode", "browser", "terminal")


def build_observation(
    *,
    timestamp: str,
    foreground: Mapping[str, Any],
    system: Mapping[str, Any],
    screen: Mapping[str, Any],
    enrichments: Mapping[str, Any] | None = None,
    observation_id: str | None = None,
) -> dict[str, Any]:
    # 不帶 previous_context：VLM 只描述「這張截圖此刻在做什麼」，過去的記憶由 AIPC 的 memory 模組管
    enrichment_values = {name: None for name in _ENRICHMENT_NAMES}
    if enrichments:
        enrichment_values.update({name: enrichments.get(name) for name in _ENRICHMENT_NAMES})

    payload = {
        "observation_id": observation_id or str(uuid4()),
        "timestamp": timestamp,
        "foreground": {
            "app": foreground.get("app"),
            "window_title": foreground.get("window_title"),
            "workspace": foreground.get("workspace"),
        },
        "system": {
            "running_apps": list(system.get("running_apps") or []),
            "idle_seconds": system.get("idle_seconds"),
        },
        "screen": {
            "screenshot_path": screen.get("screenshot_path"),
            "image_sha256": screen.get("image_sha256"),
            "perceptual_hash": screen.get("perceptual_hash"),
        },
        "enrichments": enrichment_values,
    }
    validate_observation(payload)
    return payload


def validate_observation(payload: Mapping[str, Any]) -> None:
    required = {"observation_id", "timestamp", "foreground", "system", "screen"}
    missing = required.difference(payload)
    if missing:
        raise ValueError(f"observation missing fields: {sorted(missing)}")
    for section in ("foreground", "system", "screen"):
        if not isinstance(payload[section], Mapping):
            raise ValueError(f"observation section {section!r} must be an object")
    if not isinstance(payload["system"].get("running_apps"), list):
        raise ValueError("system.running_apps must be a list")
    idle = payload["system"].get("idle_seconds")
    if idle is not None and (not isinstance(idle, (int, float)) or idle < 0):
        raise ValueError("system.idle_seconds must be non-negative or null")
    if "enrichments" in payload and not isinstance(payload["enrichments"], Mapping):
        raise ValueError("enrichments must be an object")


def validate_screen_description(payload: Mapping[str, Any]) -> None:
    """VLM 的輸出只有描述：{"text": "一句話", "error": "KeyError: 'response'" 或 null}。
    時間、id、合併、embedding 都由 AIPC 的 memory/store.py 處理，VLM 不回傳。"""
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")
    error = payload.get("error")
    if error is not None and not isinstance(error, str):
        raise ValueError("error must be a string or null")

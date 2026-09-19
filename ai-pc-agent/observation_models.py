"""Contract builders and validators shared by the local agent and MI300 client."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
from uuid import uuid4


ACTIVITY_VALUES = frozenset(
    {
        "coding",
        "debugging",
        "researching",
        "reading",
        "writing",
        "meeting",
        "communication",
        "testing",
        "designing",
        "idle",
        "unknown",
    }
)
_ENRICHMENT_NAMES = ("git", "vscode", "browser", "terminal")


def build_observation(
    *,
    timestamp: str,
    foreground: Mapping[str, Any],
    system: Mapping[str, Any],
    screen: Mapping[str, Any],
    enrichments: Mapping[str, Any] | None = None,
    previous_context: Mapping[str, Any] | None = None,
    observation_id: str | None = None,
) -> dict[str, Any]:
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
        "previous_context": deepcopy(previous_context) if previous_context else None,
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


def validate_semantic_memory(payload: Mapping[str, Any]) -> None:
    activity = payload.get("activity")
    if activity not in ACTIVITY_VALUES:
        raise ValueError(f"invalid activity: {activity!r}")
    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")
    evidence = payload.get("evidence", [])
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise ValueError("evidence must be a list of strings")

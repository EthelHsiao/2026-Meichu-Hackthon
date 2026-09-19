"""Change detection and VLM submission throttling."""

from __future__ import annotations

import re


def normalize_title(title: str | None) -> str:
    cleaned = " ".join((title or "").strip().split())
    cleaned = re.sub(r"\s+[•|]\s+\d+$", "", cleaned)
    cleaned = re.sub(r"\s+[—–-]\s+(?:LibreOffice|Microsoft Word|Microsoft PowerPoint|VS Code)$", "", cleaned, flags=re.I)
    return cleaned


class ChangeDetector:
    def __init__(self, *, min_vlm_seconds: float = 60, idle_threshold: float = 60):
        self.min_vlm_seconds = min_vlm_seconds
        self.idle_threshold = idle_threshold
        self.last_submitted_at: float | None = None

    def _meaningful_change(self, old: dict | None, new: dict) -> bool:
        if old is None:
            return True
        old_foreground = old.get("foreground", {})
        new_foreground = new.get("foreground", {})
        if old_foreground.get("app") != new_foreground.get("app"):
            return True
        if normalize_title(old_foreground.get("window_title")) != normalize_title(new_foreground.get("window_title")):
            return True
        old_system = old.get("system", {})
        new_system = new.get("system", {})
        old_idle = old_system.get("idle_seconds")
        new_idle = new_system.get("idle_seconds")
        if old_idle is not None and new_idle is not None:
            if old_idle >= self.idle_threshold > new_idle:
                return True
        if old.get("screen", {}).get("perceptual_hash") != new.get("screen", {}).get("perceptual_hash"):
            return True
        return old.get("enrichments") != new.get("enrichments")

    def should_submit(self, old: dict | None, new: dict, *, now: float) -> bool:
        meaningful = self._meaningful_change(old, new)
        if self.last_submitted_at is None:
            return meaningful
        if now - self.last_submitted_at < self.min_vlm_seconds:
            return False
        idle = new.get("system", {}).get("idle_seconds")
        if idle is not None and idle >= self.idle_threshold:
            return False
        return meaningful or now - self.last_submitted_at >= self.min_vlm_seconds

    def mark_submitted(self, observation: dict, *, now: float) -> None:
        del observation
        self.last_submitted_at = now

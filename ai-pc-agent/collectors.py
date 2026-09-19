"""Best-effort Linux desktop metadata collection without input event capture."""

from __future__ import annotations

import re
import subprocess
from typing import Callable, Iterable

from observation_models import build_observation


CommandRunner = Callable[[list[str]], str]


def subprocess_runner(args: list[str]) -> str:
    result = subprocess.run(args, check=True, capture_output=True, text=True, timeout=2)
    return result.stdout


def normalize_window_title(title: str | None) -> str | None:
    if not title:
        return None
    cleaned = " ".join(title.strip().split())
    # Linux desktop titles commonly append the application after a separator.
    cleaned = re.sub(r"\s+[•|]\s+\d+$", "", cleaned)
    cleaned = re.sub(r"\s+[—–-]\s+(?:LibreOffice|Microsoft Word|Microsoft PowerPoint|VS Code)$", "", cleaned, flags=re.I)
    return cleaned or None


def _unique_sorted(values: Iterable[str]) -> list[str]:
    return sorted({value.strip() for value in values if value.strip()})


class LinuxDesktopCollector:
    def __init__(self, runner: CommandRunner = subprocess_runner):
        self.runner = runner

    def _run(self, args: list[str]) -> str | None:
        try:
            return self.runner(args).strip()
        except (OSError, subprocess.SubprocessError, KeyError, ValueError):
            return None

    def _foreground(self) -> dict[str, str | None]:
        window_id = self._run(["xdotool", "getactivewindow"])
        title = self._run(["xdotool", "getwindowname", window_id]) if window_id else None
        pid_text = self._run(["xprop", "-id", window_id, "_NET_WM_PID"]) if window_id else None
        pid_match = re.search(r"=\s*(\d+)", pid_text or "")
        app = None
        if pid_match:
            app = self._run(["ps", "-p", pid_match.group(1), "-o", "comm="])
        return {
            "app": app.strip() if app else None,
            "window_title": normalize_window_title(title),
            "workspace": None,
        }

    def _running_apps(self) -> list[str]:
        output = self._run(["ps", "-eo", "comm="])
        return _unique_sorted(output.splitlines() if output else [])

    def _idle_seconds(self) -> int | None:
        output = self._run(["xprintidle"])
        if output is None:
            return None
        try:
            return max(0, int(float(output)) // 1000)
        except ValueError:
            return None

    def collect(self, *, timestamp: str | None = None, previous_context=None) -> dict:
        from datetime import datetime, timezone

        timestamp = timestamp or datetime.now(timezone.utc).astimezone().isoformat()
        foreground = self._foreground()
        system = {
            "running_apps": self._running_apps(),
            "idle_seconds": self._idle_seconds(),
        }
        return build_observation(
            timestamp=timestamp,
            foreground=foreground,
            system=system,
            screen={"screenshot_path": None, "image_sha256": None, "perceptual_hash": None},
            previous_context=previous_context,
        )

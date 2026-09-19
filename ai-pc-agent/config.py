"""Environment-backed defaults for the AI-PC tracker."""

import os


def _float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


LOCAL_POLL_SECONDS = _float("LOCAL_POLL_SECONDS", "10")
SCREENSHOT_SECONDS = _float("SCREENSHOT_SECONDS", "30")
MIN_VLM_SECONDS = _float("MIN_VLM_SECONDS", "60")
IDLE_THRESHOLD_SECONDS = _float("IDLE_THRESHOLD_SECONDS", "60")
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", "./screenshots")
RETRY_QUEUE_SIZE = int(os.getenv("RETRY_QUEUE_SIZE", "20"))

"""Run the universal AI-PC work-progress collector."""

import os

from agent import WorkProgressAgent
from collectors import LinuxDesktopCollector
from mi300_client import MI300Client
from screenshot import ScreenshotCapture
from config import SCREENSHOT_DIR


def build_agent() -> WorkProgressAgent:
    return WorkProgressAgent(
        collector=LinuxDesktopCollector(),
        screenshot_capture=ScreenshotCapture(directory=SCREENSHOT_DIR),
        client=MI300Client(
            base_url=os.getenv("MI300_API", "http://localhost:8000"),
            path=os.getenv("MI300_OBSERVATION_PATH", "/observations"),
        ),
    )


if __name__ == "__main__":
    print("[work-tracker] starting local collector")
    build_agent().run_forever()

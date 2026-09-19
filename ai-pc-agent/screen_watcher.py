"""Run the universal AI-PC work-progress collector."""

import os

from agent import WorkProgressAgent
from collectors import LinuxDesktopCollector
from mi300_client import MI300Client
from screenshot import ScreenshotCapture
from config import DB_PATH, EMBED_MODEL, SCREENSHOT_DIR
from memory.embedder import Embedder
from memory.store import MemoryStore


def build_agent() -> WorkProgressAgent:
    return WorkProgressAgent(
        collector=LinuxDesktopCollector(),
        screenshot_capture=ScreenshotCapture(directory=SCREENSHOT_DIR),
        client=MI300Client(
            base_url=os.getenv("MI300_API", "http://localhost:8000"),
            path=os.getenv("MI300_OBSERVATION_PATH", "/observations"),
        ),
        memory=MemoryStore(DB_PATH, Embedder(EMBED_MODEL)),
    )


if __name__ == "__main__":
    print("[work-tracker] starting local collector")
    build_agent().run_forever()

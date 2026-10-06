"""Run the universal AI-PC work-progress collector."""

from agent import WorkProgressAgent
from collectors import LinuxDesktopCollector
from mi300_client import MI300Client
from screenshot import ScreenshotCapture
from config import (
    DB_PATH,
    EMBED_MODEL,
    MI300_BASE_URL,
    MI300_SCREEN_OBSERVATION_PATH,
    SCREENSHOT_DIR,
    SCREENSHOT_RETENTION_MINUTES,
)
from memory.embedder import Embedder
from memory.store import MemoryStore


def build_agent() -> WorkProgressAgent:
    return WorkProgressAgent(
        collector=LinuxDesktopCollector(),
        screenshot_capture=ScreenshotCapture(
            directory=SCREENSHOT_DIR, retention_minutes=SCREENSHOT_RETENTION_MINUTES
        ),
        client=MI300Client(base_url=MI300_BASE_URL, path=MI300_SCREEN_OBSERVATION_PATH),
        memory=MemoryStore(DB_PATH, Embedder(EMBED_MODEL)),
    )


if __name__ == "__main__":
    print("[work-tracker] starting local collector")
    build_agent().run_forever()

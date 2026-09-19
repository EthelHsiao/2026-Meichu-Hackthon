"""Screenshot capture with local hashing and configurable retention."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from uuid import uuid4

class ScreenshotCapture:
    def __init__(self, directory: str = "./screenshots", max_width: int = 1280, quality: int = 60):
        self.directory = Path(directory)
        self.max_width = max_width
        self.quality = quality

    def capture(self) -> tuple[dict, bytes]:
        import mss
        from PIL import Image

        self.directory.mkdir(parents=True, exist_ok=True)
        with mss.mss() as screen:
            monitor = screen.monitors[1] if len(screen.monitors) > 1 else screen.monitors[0]
            raw = screen.grab(monitor)
            image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        if image.width > self.max_width:
            ratio = self.max_width / image.width
            image = image.resize((self.max_width, int(image.height * ratio)))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self.quality, optimize=True)
        data = buffer.getvalue()
        path = self.directory / f"{uuid4()}.jpg"
        path.write_bytes(data)
        return {
            "screenshot_path": str(path),
            "image_sha256": hashlib.sha256(data).hexdigest(),
            "perceptual_hash": self._average_hash(image),
        }, data

    @staticmethod
    def _average_hash(image: Image.Image) -> str:
        small = image.convert("L").resize((8, 8))
        pixels = list(small.getdata())
        average = sum(pixels) / len(pixels)
        return "".join("1" if pixel >= average else "0" for pixel in pixels)

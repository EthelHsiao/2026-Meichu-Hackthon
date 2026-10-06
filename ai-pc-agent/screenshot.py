"""Screenshot capture with local hashing and configurable retention."""

from __future__ import annotations

import hashlib
import io
import time
from pathlib import Path
from uuid import uuid4

class ScreenshotCapture:
    def __init__(
        self,
        directory: str = "./screenshots",
        max_width: int = 1280,
        quality: int = 60,
        retention_minutes: float = 10.0,
    ):
        self.directory = Path(directory)
        self.max_width = max_width
        self.quality = quality
        self.retention_minutes = retention_minutes

    def capture(self) -> tuple[dict, bytes]:
        import mss
        from PIL import Image

        self.directory.mkdir(parents=True, exist_ok=True)
        # 在寫入新檔之前先清，這樣「剛拍的這張」永遠不會被自己的保留規則刪掉，
        # retention_minutes=0 也就等於「只留當下這張」。
        self.prune()
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

    def prune(self, now: float | None = None) -> int:
        """刪掉超過 retention_minutes 的舊截圖，回傳刪掉幾張。

        刪檔失敗（權限、檔案剛好被別的程序拿走）不該讓截圖流程整個停掉，
        所以這裡吞掉 OSError 繼續處理下一個檔案。
        """
        if self.retention_minutes < 0 or not self.directory.is_dir():
            return 0
        cutoff = (now if now is not None else time.time()) - self.retention_minutes * 60
        removed = 0
        for path in self.directory.glob("*.jpg"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    @staticmethod
    def _average_hash(image: Image.Image) -> str:
        small = image.convert("L").resize((8, 8))
        pixels = list(small.getdata())
        average = sum(pixels) / len(pixels)
        return "".join("1" if pixel >= average else "0" for pixel in pixels)

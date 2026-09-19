"""輕量的記憶體內測試紀錄，給 debug dashboard 用（見 docs/api.html §⑧）。
不是 memory/ 那套長期記憶——純粹是「這次測試傳了什麼、收到什麼」的可視化用途，
重啟就清空，不落地、不影響 memories 表。
"""
from __future__ import annotations

import base64
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class TraceEntry:
    ts: float
    kind: str  # "screen_observation" | "chat_reply" | "homework_analysis" | "touch"
    request: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    image_b64: Optional[str] = None  # 縮圖用，跟 memory 不同，這裡刻意允許暫存圖片

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "ts_iso": datetime.fromtimestamp(self.ts).astimezone().isoformat(timespec="seconds"),
            "kind": self.kind,
            "request": self.request,
            "response": self.response,
            "image_b64": self.image_b64,
        }


class TraceLog:
    def __init__(self, max_items: int = 200):
        self._items: deque[TraceEntry] = deque(maxlen=max_items)

    def add(
        self, kind: str, request: dict[str, Any], response: dict[str, Any], *, image_bytes: bytes | None = None
    ) -> None:
        image_b64 = base64.b64encode(image_bytes).decode("ascii") if image_bytes else None
        self._items.appendleft(TraceEntry(ts=time.time(), kind=kind, request=request, response=response, image_b64=image_b64))

    def recent(self, n: int = 50) -> list[TraceEntry]:
        return list(self._items)[:n]

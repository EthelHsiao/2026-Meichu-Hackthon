"""語音 -> 文字。

2026-09-20 音訊來源已確定：ESP32 主板的 INMP441，經第①節 WebSocket 送到 AIPC，
是 int16、16kHz、mono 的 PCM（不是 AIPC 本機麥克風）。這裡把這個 PCM 轉送到本機
已經在跑的 STT 服務（stt/backend/main.py，ws://127.0.0.1:8765/ws/audio，格式見
docs/api.html §②），STT 服務自己做 VAD／draft／final，這裡只在意 final。

原本的 stub 是同步的 `transcribe(audio) -> str`（一次丟一整段錄音進去），但
麥克風資料是連續串流、不是一次性的固定緩衝區，所以改成非同步的串流介面：
建一個 SttBridge、持續餵 PCM 進去，final 逐字稿透過 callback 送出。
"""
from __future__ import annotations

import asyncio
import json
from typing import Callable, Optional

import numpy as np
from websockets.client import connect
from websockets.exceptions import WebSocketException

import config

CHUNK_SAMPLES = 512  # 跟 docs/api.html §② 的合約一致：每包 512 個 float32 sample


class SttBridge:
    """使用方式（main.py）：
        bridge = SttBridge(on_final=lambda text: ...)
        asyncio.create_task(bridge.run_forever())   # 常駐：連線、斷線自動重連、依序送音訊
        bridge.feed_pcm_int16(pcm_bytes)             # 收到 ESP32 mic frame 就丟進來（不會卡、不會丟例外）

    STT 服務沒起來時音訊直接丟掉，服務起來後自動接上；所有 frame 由同一個送出迴圈
    依序送，不會因為每個 frame 各開一個 task 而把音訊順序打亂。
    """

    QUEUE_FRAMES = 200   # 約 3 秒的 ESP32 音訊；STT 卡住時丟最舊的，不讓記憶體一直長

    def __init__(
        self,
        url: str | None = None,
        *,
        on_final: Optional[Callable[[str], None]] = None,
        on_level: Optional[Callable[[dict], None]] = None,
    ):
        self.url = url or config.STT_WS_URL
        self.on_final = on_final
        self.on_level = on_level  # {"rms":..,"peak":..,"vad":"speech"|"silence",...}，debug dashboard 用
        self._ws = None
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=self.QUEUE_FRAMES)

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def feed_pcm_int16(self, pcm: bytes) -> None:
        """pcm 是 ESP32 送來的 16-bit little-endian PCM；沒連上 STT 就丟掉。"""
        if self._ws is None:
            return
        if self._queue.full():
            self._queue.get_nowait()
        self._queue.put_nowait(pcm)

    async def run_forever(self) -> None:
        while True:
            try:
                async with connect(self.url, max_size=None) as ws:
                    self._ws = ws
                    print(f"[stt] 連上 {self.url}")
                    sender = asyncio.create_task(self._send_loop(ws))
                    try:
                        await self._recv_loop(ws)
                    finally:
                        sender.cancel()
            except (OSError, TimeoutError, WebSocketException) as exc:
                if self._ws is None:
                    print(f"[stt] 連不上 {self.url}，{config.ESP32_WS_RECONNECT_SECONDS:.0f} 秒後重試：{exc}")
            self._ws = None
            while not self._queue.empty():
                self._queue.get_nowait()
            await asyncio.sleep(config.ESP32_WS_RECONNECT_SECONDS)

    async def _send_loop(self, ws) -> None:
        while True:
            pcm = await self._queue.get()
            samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
            payload = samples.astype("<f4").tobytes()
            step = CHUNK_SAMPLES * 4  # 4 bytes / float32
            for i in range(0, len(payload), step):
                await ws.send(payload[i : i + step])

    async def _recv_loop(self, ws) -> None:
        async for raw in ws:
            if not isinstance(raw, str):
                continue  # 不會有 server -> client 的 binary，忽略保險
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "final" and isinstance(msg.get("text"), str) and self.on_final:
                self.on_final(msg["text"])
            elif msg.get("type") == "audio_level" and self.on_level:
                self.on_level(msg)

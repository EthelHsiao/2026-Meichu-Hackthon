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
    """使用方式：
        bridge = SttBridge(on_final=lambda text: ...)
        await bridge.connect()
        await bridge.send_pcm_int16(pcm_bytes)   # 收到 ESP32 mic frame 就轉送
        await bridge.stop_utterance()            # 一句話講完（例如 VAD 偵測到靜音）
        await bridge.close()
    """

    def __init__(self, url: str | None = None, *, on_final: Optional[Callable[[str], None]] = None):
        self.url = url or config.STT_WS_URL
        self.on_final = on_final
        self._ws = None
        self._recv_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        self._ws = await connect(self.url, max_size=None)
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def close(self) -> None:
        if self._recv_task is not None:
            self._recv_task.cancel()
        if self._ws is not None:
            await self._ws.close()

    async def _recv_loop(self) -> None:
        try:
            async for raw in self._ws:
                if not isinstance(raw, str):
                    continue  # 不會有 server -> client 的 binary，忽略保險
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "final" and isinstance(msg.get("text"), str) and self.on_final:
                    self.on_final(msg["text"])
        except (WebSocketException, asyncio.CancelledError):
            pass

    async def send_pcm_int16(self, pcm: bytes) -> None:
        """pcm 是 ESP32 送來的 16-bit little-endian PCM，轉成 stt/backend 要的
        float32（正規化到 -1..1）、512 sample 一包送出。"""
        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        payload = samples.astype("<f4").tobytes()
        step = CHUNK_SAMPLES * 4  # 4 bytes / float32
        for i in range(0, len(payload), step):
            await self._ws.send(payload[i : i + step])

    async def stop_utterance(self) -> None:
        await self._ws.send(json.dumps({"type": "stop"}))

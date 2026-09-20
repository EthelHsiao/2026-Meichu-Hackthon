"""ESP32 主板 <-> AIPC 的 WebSocket 橋接。訊息格式見 ../protocol.py，總覽見 docs/api.html §①。

2026-09-20：取代原本規劃、但從未實作的 USB Serial 橋（原 sensing/serial_bridge.py）。
連線/重連邏輯比照 esp32-bringup/tools/receive_telemetry.py 已經驗證過的做法。
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterable, Callable, Iterable, Optional, Union

from websockets.client import connect
from websockets.exceptions import WebSocketException

import config
from protocol import (
    BuzzCommand,
    ClearCommand,
    Expr,
    ExprCommand,
    Heartbeat,
    SayCommand,
    TelemetrySample,
    TouchEvent,
    parse_line,
)
from sensing.gestures import GestureDetector

EventHandler = Callable[[Union[TouchEvent, Heartbeat]], None]
MicHandler = Callable[[bytes], None]
TelemetryHandler = Callable[[TelemetrySample], None]


class Esp32WsClient:
    """常駐連線：收到 touch/心跳 JSON 就丟給 on_event；收到 binary frame（麥克風
    PCM）就丟給 on_mic；telemetry（fsr/imu）frame 同時做兩件事——餵去 gestures
    判斷 squeeze/pat/shake/lift/putdown（結果一樣經 on_event 送出，double_tap
    是例外，韌體直接送事件），原始數值另外丟給 on_telemetry（給 dashboard 即時
    顯示用，不影響 on_event 原本「只收離散手勢事件」的約定）。
    send() 可以把 SayCommand/ExprCommand/BuzzCommand 下發給 ESP32。斷線會照
    config.ESP32_WS_RECONNECT_SECONDS 自動重試，不會讓呼叫端的迴圈跟著死掉。
    """

    def __init__(
        self,
        url: str | None = None,
        *,
        on_event: Optional[EventHandler] = None,
        on_mic: Optional[MicHandler] = None,
        on_telemetry: Optional[TelemetryHandler] = None,
    ):
        self.url = url or config.ESP32_WS_URL
        self.on_event = on_event
        self.on_mic = on_mic
        self.on_telemetry = on_telemetry
        self._ws = None
        self.gestures = GestureDetector()   # telemetry 原始數值 -> squeeze/pat/shake/lift/putdown

    async def run_forever(self) -> None:
        """常駐收訊迴圈；斷線自動重連。放進 asyncio.create_task() 背景跑，不會回傳。"""
        while True:
            try:
                async with connect(
                    self.url, open_timeout=5, close_timeout=1, ping_interval=20, ping_timeout=10
                ) as ws:
                    self._ws = ws
                    async for raw in ws:
                        self._handle(raw)
            except (OSError, TimeoutError, WebSocketException):
                self._ws = None
                await asyncio.sleep(config.ESP32_WS_RECONNECT_SECONDS)

    def _handle(self, raw) -> None:
        # on_event/on_mic 是呼叫端（main.py）的callback，裡面會寫記憶體/資料庫；
        # 這裡的例外處理是刻意的防禦邊界——callback 出錯不該讓 run_forever() 的
        # async for 迴圈跟著死掉（那樣連線就整個斷了，比 callback 本身失敗更糟）。
        try:
            if isinstance(raw, (bytes, bytearray)):
                if self.on_mic:
                    self.on_mic(raw)
                return
            event = parse_line(raw)  # telemetry frame 沒有 "t" 只有 "type"，parse_line 會回 TelemetrySample
            if isinstance(event, TelemetrySample):
                if self.on_telemetry:
                    self.on_telemetry(event)
                # 手勢判斷（squeeze/pat/shake/lift/putdown；double_tap 例外，韌體直接送事件）
                # 走 on_event，跟離散事件同一條路，不受上面 on_telemetry 影響。
                events = self.gestures.feed(json.loads(raw))
            elif event is not None:
                events = [event]
            else:
                events = []
            if self.on_event:
                for e in events:
                    self.on_event(e)
        except Exception as exc:  # noqa: BLE001
            print(f"[esp32] 處理收到的訊息時發生錯誤: {exc}")

    async def send(self, cmd: Union[SayCommand, ExprCommand, BuzzCommand, ClearCommand]) -> None:
        if self._ws is None:
            raise ConnectionError("ESP32 WebSocket 尚未連線，無法送出指令")
        await self._ws.send(cmd.to_line().rstrip("\n"))

    async def say_stream(
        self,
        chunks: Union[AsyncIterable[str], Iterable[str]],
        expr: Optional[Expr] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> str:
        """LLM 邊生成邊送到 LCD：第一段馬上送（帶 expr），之後每
        config.ESP32_STREAM_FLUSH_SECONDS 秒合併一次送 done=False，最後送 done=True。
        ESP32 沒連線或中途斷線時照樣把 chunks 讀完、回傳整句，只是不再送，
        不會拖慢或打斷呼叫端（整句仍可寫記憶）。"""
        full, pending = [], ""
        first, connected = True, True
        last_flush = clock() - config.ESP32_STREAM_FLUSH_SECONDS

        async def flush(done: bool) -> None:
            nonlocal first, pending, last_flush, connected
            if connected:
                try:
                    await self.send(SayCommand(expr if first else None, pending, done=done))
                except (ConnectionError, OSError, WebSocketException) as exc:
                    print(f"[esp32] 串流送出失敗，這句剩下的不送了: {exc}")
                    connected = False
            first, pending, last_flush = False, "", clock()

        async for chunk in _aiter(chunks):
            if not chunk:
                continue
            full.append(chunk)
            pending += chunk
            if clock() - last_flush >= config.ESP32_STREAM_FLUSH_SECONDS:
                await flush(done=False)
        await flush(done=True)
        return "".join(full)


async def _aiter(chunks):
    """同時接受 async generator（串流 HTTP 回應）跟一般 list/generator。"""
    if hasattr(chunks, "__aiter__"):
        async for chunk in chunks:
            yield chunk
    else:
        for chunk in chunks:
            yield chunk

"""ESP32 主板 <-> AIPC 的 WebSocket 橋接。訊息格式見 ../protocol.py，總覽見 docs/api.html §①。

2026-09-20：取代原本規劃、但從未實作的 USB Serial 橋（原 sensing/serial_bridge.py）。
連線/重連邏輯比照 esp32-bringup/tools/receive_telemetry.py 已經驗證過的做法。
"""
from __future__ import annotations

import asyncio
import json
from typing import Callable, Optional, Union

from websockets.client import connect
from websockets.exceptions import WebSocketException

import config
from protocol import BuzzCommand, ExprCommand, Heartbeat, SayCommand, TouchEvent, parse_line

EventHandler = Callable[[Union[TouchEvent, Heartbeat]], None]
MicHandler = Callable[[bytes], None]
TelemetryHandler = Callable[[dict], None]


class Esp32WsClient:
    """常駐連線：收到 touch/心跳 JSON 就丟給 on_event；收到 binary frame（麥克風
    PCM）就丟給 on_mic；telemetry（fsr/imu，見 esp32-bringup/docs/telemetry.md 的
    schema）就丟給 on_telemetry——只在有人註冊這個 callback 時才會多解析一次
    JSON，沒人要看 telemetry 時零額外成本。send() 可以把 SayCommand/ExprCommand/
    BuzzCommand 下發給 ESP32。斷線會照 config.ESP32_WS_RECONNECT_SECONDS 自動
    重試，不會讓呼叫端的迴圈跟著死掉。
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
            # telemetry 用 "type" 欄位（不是 "t"），parse_line 認不得、會回 None——
            # 只有真的有人註冊 on_telemetry 才多解一次 JSON，沒人要看 telemetry
            # 時不用為這條 20Hz 的高頻率訊息多付一次解析成本。
            if self.on_telemetry:
                try:
                    msg = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    msg = None
                if isinstance(msg, dict) and msg.get("type") == "telemetry":
                    self.on_telemetry(msg)
                    return
            event = parse_line(raw)  # telemetry frame 沒有 "t" 欄位，parse_line 會回 None，安全略過
            if event is not None and self.on_event:
                self.on_event(event)
        except Exception as exc:  # noqa: BLE001
            print(f"[esp32] 處理收到的訊息時發生錯誤: {exc}")

    async def send(self, cmd: Union[SayCommand, ExprCommand, BuzzCommand]) -> None:
        if self._ws is None:
            raise ConnectionError("ESP32 WebSocket 尚未連線，無法送出指令")
        await self._ws.send(cmd.to_line().rstrip("\n"))

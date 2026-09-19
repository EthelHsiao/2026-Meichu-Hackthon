"""從 ESP32 的 telemetry 原始數值判斷手勢：squeeze 捏 / pat 拍 / shake 搖 / lift 拿起 / putdown 放下。

ESP32 只送原始數值（每 50ms 一包，格式見 docs/api.html §①）：
    {"type":"telemetry","uptime_ms":3200,"fsr":{"raw":[120,230]},
     "imu":{"ok":true,"accel_m_s2":[x,y,z],"gyro_rad_s":[x,y,z]}, ...}
double_tap 由韌體本地判斷後直接送事件，這裡不重複判斷。
時間用 ESP32 的 uptime_ms，不受 WiFi 延遲抖動影響。門檻全在 config.py，都是 [CANDIDATE]。

調門檻（電腦先連上 ESP32 的 WiFi）：
    python -m sensing.gestures --live
"""
from __future__ import annotations

import math
from collections import deque
from typing import Optional

import config
from protocol import TouchEvent

GRAVITY = 9.80665
ADC_MAX = 4095


def _press_strength(peak_raw: int) -> float:
    return round(min(1.0, max(0.0, (peak_raw - config.FSR_PRESS_RAW) / (ADC_MAX - config.FSR_PRESS_RAW))), 2)


class GestureDetector:
    def __init__(self):
        self._down_at: list[Optional[int]] = [None, None]   # 每個 FSR 開始壓住的時間
        self._peak = [0, 0]                                   # 這次壓住的最大值
        self._squeezed = False                                # 這次同時壓住已經送過 squeeze
        self._pending_pat: Optional[tuple[int, int, int, int]] = None   # (哪個 FSR, 放開時間, 壓多久, 最大值)
        self._accel: deque[tuple[int, float]] = deque()
        self._last_shake = -10**9
        self._resting: Optional[bool] = None                  # None = 還不知道
        self._still_since: Optional[int] = None
        self._move_since: Optional[int] = None

    def feed(self, frame: dict) -> list[TouchEvent]:
        """餵一包 telemetry，回傳這一包判斷出來的手勢（大多數時候是空的）。"""
        t = frame.get("uptime_ms")
        if not isinstance(t, (int, float)):
            return []
        t = int(t)
        events = []
        raw = (frame.get("fsr") or {}).get("raw")
        if isinstance(raw, list) and len(raw) >= 2:
            events += self._fsr(t, raw[0], raw[1])
        imu = frame.get("imu") or {}
        if imu.get("ok") and imu.get("accel_m_s2") and imu.get("gyro_rad_s"):
            events += self._imu(t, imu["accel_m_s2"], imu["gyro_rad_s"])
        return events

    # ---- FSR：捏（兩個一起壓久一點）、拍（壓一下很快放開）----
    def _fsr(self, t: int, *raw: int) -> list[TouchEvent]:
        out = []
        pressed = [r > config.FSR_PRESS_RAW for r in raw]
        for i in (0, 1):
            if pressed[i]:
                if self._down_at[i] is None:
                    self._down_at[i], self._peak[i] = t, raw[i]
                self._peak[i] = max(self._peak[i], raw[i])
            elif self._down_at[i] is not None:   # 剛放開
                dur = t - self._down_at[i]
                self._down_at[i] = None
                if self._squeezed or dur > config.PAT_MAX_MS:
                    continue
                if self._pending_pat and self._pending_pat[0] == i and i == 0:
                    self._pending_pat = None   # FSR1 拍第二下 = 韌體會送 double_tap，不算拍
                else:
                    self._pending_pat = (i, t, dur, self._peak[i])

        if all(pressed) and not self._squeezed:
            both_since = max(self._down_at[0], self._down_at[1])
            if t - both_since >= config.SQUEEZE_MIN_MS:
                self._squeezed = True
                self._pending_pat = None
                out.append(TouchEvent("squeeze", _press_strength(min(self._peak)), t - both_since))
        if not any(pressed):
            self._squeezed = False

        if self._pending_pat and t - self._pending_pat[1] >= config.PAT_CONFIRM_MS:
            _, _, dur, peak = self._pending_pat
            self._pending_pat = None
            out.append(TouchEvent("pat", _press_strength(peak), dur))
        return out

    # ---- IMU：搖（加速度大幅變化）、拿起／放下（靜止 <-> 移動）----
    def _imu(self, t: int, accel: list[float], gyro: list[float]) -> list[TouchEvent]:
        out = []
        a = math.sqrt(sum(v * v for v in accel))
        g = math.sqrt(sum(v * v for v in gyro))

        self._accel.append((t, a))
        while self._accel and t - self._accel[0][0] > config.SHAKE_WINDOW_MS:
            self._accel.popleft()
        values = [v for _, v in self._accel]
        p2p = max(values) - min(values)
        if len(values) >= 3 and p2p >= config.SHAKE_ACCEL_P2P and t - self._last_shake >= config.SHAKE_COOLDOWN_MS:
            self._last_shake = t
            span = t - self._accel[0][0]
            out.append(TouchEvent("shake", round(min(1.0, p2p / (2 * config.SHAKE_ACCEL_P2P)), 2), span))

        still = g < config.STILL_GYRO and abs(a - GRAVITY) < config.STILL_ACCEL_DEV
        if still:
            self._move_since = None
            self._still_since = self._still_since if self._still_since is not None else t
            if self._resting is not True and t - self._still_since >= config.REST_MIN_MS:
                if self._resting is False:
                    out.append(TouchEvent("putdown", 1.0, t - self._still_since))
                self._resting = True
        else:
            self._still_since = None
            self._move_since = self._move_since if self._move_since is not None else t
            if self._resting is True and t - self._move_since >= config.MOVE_MIN_MS:
                self._resting = False
                out.append(TouchEvent("lift", 1.0, t - self._move_since))
        return out


def _live():
    """連上 ESP32，一直印 FSR / IMU 關鍵數值和判斷出來的手勢，用來調 config.py 的門檻。"""
    import asyncio
    import json

    from websockets.client import connect

    async def run():
        detector = GestureDetector()
        async with connect(config.ESP32_WS_URL) as ws:
            print(f"連上 {config.ESP32_WS_URL}，Ctrl+C 結束")
            async for raw in ws:
                if isinstance(raw, (bytes, bytearray)) or '"telemetry"' not in raw:
                    continue
                frame = json.loads(raw)
                fsr = (frame.get("fsr") or {}).get("raw")
                imu = frame.get("imu") or {}
                a = g = float("nan")
                if imu.get("ok"):
                    a = math.sqrt(sum(v * v for v in imu["accel_m_s2"]))
                    g = math.sqrt(sum(v * v for v in imu["gyro_rad_s"]))
                line = f"fsr={fsr}  |a|={a:5.2f}  |gyro|={g:4.2f}"
                for event in detector.feed(frame):
                    line += f"   <== {event.kind} strength={event.strength} dur_ms={event.dur_ms}"
                print(line)

    asyncio.run(run())


if __name__ == "__main__":
    import sys

    if "--live" in sys.argv:
        _live()
    else:
        print(__doc__)

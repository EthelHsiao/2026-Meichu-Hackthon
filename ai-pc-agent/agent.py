"""Polling orchestration for the local work-progress tracker."""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Any

from detector import ChangeDetector, normalize_title
from config import LOCAL_POLL_SECONDS, MIN_VLM_SECONDS, RETRY_QUEUE_SIZE, SCREENSHOT_SECONDS


def memory_fields(observation: dict[str, Any], description: dict[str, Any]) -> dict[str, str]:
    """observation + VLM 輸出 -> store.add_or_extend 需要的欄位。
    state_key 用作業系統讀到的 app + 視窗標題 + 錯誤類型，不用 VLM 寫的句子（每次用詞都不同）。
    error 從 2026-09-20 起是 {"kind","code","message","file","line"} 或 null
    （見 bench/screen-schema.json），error_sig 沿用舊行為從 message 冒號前段取
    （例如 "KeyError: 'response'" -> "KeyError"），message 是 null 時退回用
    kind（例如 "runtime"），這樣同一類錯誤跨多張截圖還是能合併/加權。"""
    foreground = observation.get("foreground", {})
    app = foreground.get("app") or ""
    error = description.get("error") or {}
    error_message = error.get("message") or ""
    error_sig = error_message.split(":", 1)[0].strip() if error_message else (error.get("kind") or "")
    return {
        "app": app,
        "state_key": "|".join([app, normalize_title(foreground.get("window_title")), error_sig]),
        "error_sig": error_sig,
        "ts": observation.get("timestamp"),
    }


def screen_memory_text(description: dict[str, Any]) -> str:
    """screen 記憶要存的一行摘要：以 activity 為主，有錯誤訊息時併進來——
    bench/screen-prompt.txt 要求 activity 不要重複描述錯誤內容，所以錯誤
    訊息不併進來的話，RAG 對「這個 KeyError 怎麼修」這類問題會撈不到。"""
    text = description.get("activity") or description.get("app") or "（無法辨識畫面內容）"
    error = description.get("error")
    if error and error.get("message"):
        text = f"{text}（錯誤：{error['message']}）"
    return text


class BoundedRetryQueue:
    def __init__(self, max_items: int = 20):
        self._items = deque(maxlen=max_items)

    def put(self, item) -> None:
        self._items.append(item)

    def get(self):
        return self._items.popleft()

    def size(self) -> int:
        return len(self._items)


class WorkProgressAgent:
    def __init__(
        self,
        collector,
        screenshot_capture,
        client,
        *,
        memory=None,
        detector=None,
        local_poll_seconds: float = LOCAL_POLL_SECONDS,
        screenshot_seconds: float = SCREENSHOT_SECONDS,
        retry_queue: BoundedRetryQueue | None = None,
        clock=time.monotonic,
    ):
        self.collector = collector
        self.screenshot_capture = screenshot_capture
        self.client = client
        self.memory = memory  # memory.store.MemoryStore；None 就只送不存（測試用）
        self.detector = detector or ChangeDetector(min_vlm_seconds=MIN_VLM_SECONDS)
        self.local_poll_seconds = local_poll_seconds
        self.screenshot_seconds = screenshot_seconds
        self.retry_queue = retry_queue or BoundedRetryQueue(RETRY_QUEUE_SIZE)
        self.clock = clock
        self.previous = None
        self.last_capture_at = None
        self.last_capture = (None, b"")

    def _needs_capture(self, state: dict[str, Any], now: float) -> bool:
        if self.last_capture_at is None:
            return True
        if now - self.last_capture_at >= self.screenshot_seconds:
            return True
        if self.previous is None:
            return True
        old_foreground = self.previous.get("foreground", {})
        new_foreground = state.get("foreground", {})
        return (
            old_foreground.get("app") != new_foreground.get("app")
            or normalize_title(old_foreground.get("window_title"))
            != normalize_title(new_foreground.get("window_title"))
        )

    def _deliver(self, state: dict[str, Any], image: bytes) -> None:
        """送給 VLM，拿回結構化畫面觀察後寫進記憶。失敗會丟例外，由呼叫端放進重試佇列。"""
        result = self.client.submit_observation(state, image)
        if self.memory is not None:
            self.memory.add_or_extend("screen", screen_memory_text(result), **memory_fields(state, result))

    def _deliver_retries(self) -> None:
        if not self.retry_queue.size():
            return
        item = self.retry_queue.get()
        try:
            self._deliver(*item)
        except Exception:  # noqa: BLE001 - keep the collector alive across network/model failures
            self.retry_queue.put(item)

    def run_once(self, *, now: float | None = None) -> dict[str, Any]:
        now = self.clock() if now is None else now
        state = self.collector.collect()
        if self._needs_capture(state, now):
            try:
                screen, image = self.screenshot_capture.capture()
                state["screen"].update(screen)
                self.last_capture = (screen, image)
                self.last_capture_at = now
            except Exception:  # noqa: BLE001 - screenshot failure should not stop metadata collection
                pass
        # last_capture[0] is None until the first successful capture. Without this guard,
        # an environment where screenshot capture always fails (e.g. no DISPLAY available
        # to this process) would keep submitting the empty b"" placeholder from __init__
        # to MI300 forever instead of just not submitting.
        if self.detector.should_submit(self.previous, state, now=now) and self.last_capture[0] is not None:
            image = self.last_capture[1]
            try:
                self._deliver(state, image)
                self.detector.mark_submitted(state, now=now)
            except Exception:  # noqa: BLE001 - queue for a later retry
                self.retry_queue.put((state, image))
        self._deliver_retries()
        self.previous = state
        return state

    def run_forever(self) -> None:
        while True:
            started = self.clock()
            self.run_once(now=started)
            time.sleep(max(0, self.local_poll_seconds - (self.clock() - started)))

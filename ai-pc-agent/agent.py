"""Polling orchestration for the local work-progress tracker."""

from __future__ import annotations

import os
import time
from collections import deque
from typing import Any

from detector import ChangeDetector, normalize_title
from config import LOCAL_POLL_SECONDS, MIN_VLM_SECONDS, RETRY_QUEUE_SIZE, SCREENSHOT_SECONDS


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
        detector=None,
        local_poll_seconds: float = LOCAL_POLL_SECONDS,
        screenshot_seconds: float = SCREENSHOT_SECONDS,
        retry_queue: BoundedRetryQueue | None = None,
        clock=time.monotonic,
    ):
        self.collector = collector
        self.screenshot_capture = screenshot_capture
        self.client = client
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

    def _deliver_retries(self) -> None:
        if not self.retry_queue.size():
            return
        item = self.retry_queue.get()
        try:
            self.client.submit_observation(*item)
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
        if self.detector.should_submit(self.previous, state, now=now):
            image = self.last_capture[1]
            try:
                self.client.submit_observation(state, image)
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

import unittest

from agent import BoundedRetryQueue, WorkProgressAgent, memory_fields, screen_memory_text
from memory.store import MemoryStore
from tests.test_memory import FakeEmbedder


class AgentTests(unittest.TestCase):
    def test_failed_delivery_is_bounded_and_does_not_raise(self):
        queue = BoundedRetryQueue(max_items=2)
        queue.put(({"observation_id": "1"}, b"1"))
        queue.put(({"observation_id": "2"}, b"2"))
        queue.put(({"observation_id": "3"}, b"3"))
        self.assertEqual(queue.size(), 2)
        self.assertEqual(queue.get()[0]["observation_id"], "2")

    def test_memory_fields_use_os_metadata_for_state_key(self):
        obs = {"timestamp": "2026-09-19T09:00:00+08:00",
               "foreground": {"app": "code", "window_title": "main.py - VS Code"}}
        error = {"kind": "runtime", "code": None, "message": "KeyError: 'response'", "file": None, "line": None}
        fields = memory_fields(obs, {"activity": "debug", "error": error})
        self.assertEqual(fields["state_key"], "code|main.py|KeyError")
        self.assertEqual(fields["error_sig"], "KeyError")
        self.assertEqual(memory_fields(obs, {"activity": "x", "error": None})["error_sig"], "")

    def test_memory_fields_falls_back_to_error_kind_when_message_missing(self):
        obs = {"timestamp": "2026-09-19T09:00:00+08:00", "foreground": {"app": "code"}}
        error = {"kind": "runtime", "code": None, "message": None, "file": None, "line": None}
        self.assertEqual(memory_fields(obs, {"activity": "x", "error": error})["error_sig"], "runtime")

    def test_screen_memory_text_appends_error_message_to_activity(self):
        self.assertEqual(
            screen_memory_text({"activity": "在 main.py 除錯", "error": None}),
            "在 main.py 除錯",
        )
        self.assertEqual(
            screen_memory_text({
                "activity": "在 main.py 除錯",
                "error": {"kind": "runtime", "message": "KeyError: 'response'"},
            }),
            "在 main.py 除錯（錯誤：KeyError: 'response'）",
        )
        self.assertEqual(screen_memory_text({"activity": None, "app": None, "error": None}), "（無法辨識畫面內容）")

    def test_vlm_result_is_written_to_memory_and_merged(self):
        class Collector:
            def __init__(self):
                self.t = 0
            def collect(self):
                self.t += 1
                return {"timestamp": f"2026-09-19T09:0{self.t}:00+08:00",
                        "foreground": {"app": "code", "window_title": "main.py"},
                        "system": {"idle_seconds": 0}, "screen": {}, "enrichments": None}

        class Client:
            def submit_observation(self, observation, image):
                return {
                    "app": "code", "activity": "在 main.py 遇到 KeyError", "evidence": [],
                    "error": {"kind": "runtime", "code": None, "message": "KeyError: 'response'",
                              "file": None, "line": None},
                    "cause": None, "missing_context": [],
                }

        class Detector:  # 每次都送，專心測寫入記憶
            def should_submit(self, old, new, *, now): return True
            def mark_submitted(self, observation, *, now): pass

        class Capture:
            def capture(self): return {}, b"jpeg"

        store = MemoryStore(":memory:", FakeEmbedder())
        agent = WorkProgressAgent(Collector(), Capture(), Client(), memory=store, detector=Detector())
        agent.run_once(now=0)
        agent.run_once(now=60)
        [m] = store.recent(10)  # 同一個狀態 → 合併成一筆
        self.assertEqual((m.ts_start, m.ts_end), ("2026-09-19T09:01:00+08:00", "2026-09-19T09:02:00+08:00"))
        self.assertEqual(m.error_sig, "KeyError")

    def test_never_submits_when_screenshot_capture_always_fails(self):
        """實測抓到的真實案例：AIPC 的 systemd 服務沒有 DISPLAY 環境變數時，
        screenshot_capture.capture() 每次都會拋例外。沒有這個保護，run_once 會
        一直把 __init__ 預設的空 b"" 圖片送去 MI300，而不是乾脆不送。"""
        class FailingCapture:
            def capture(self):
                raise RuntimeError("no DISPLAY")

        class Client:
            def submit_observation(self, observation, image):
                raise AssertionError("一次成功的截圖都沒有時，不該呼叫 MI300")

        class Collector:
            def collect(self):
                return {
                    "timestamp": "2026-09-19T09:00:00+08:00", "foreground": {},
                    "system": {}, "screen": {}, "enrichments": None,
                }

        store = MemoryStore(":memory:", FakeEmbedder())
        agent = WorkProgressAgent(Collector(), FailingCapture(), Client(), memory=store)
        agent.run_once(now=0)
        self.assertEqual(store.recent(10), [])


if __name__ == "__main__":
    unittest.main()

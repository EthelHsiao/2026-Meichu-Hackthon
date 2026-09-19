import unittest

from agent import BoundedRetryQueue, WorkProgressAgent, memory_fields
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
        fields = memory_fields(obs, {"text": "debug", "error": "KeyError: 'response'"})
        self.assertEqual(fields["state_key"], "code|main.py|KeyError")
        self.assertEqual(fields["error_sig"], "KeyError")
        self.assertEqual(memory_fields(obs, {"text": "x", "error": None})["error_sig"], "")

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
                return {"text": "在 main.py 遇到 KeyError", "error": "KeyError: 'response'"}

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


if __name__ == "__main__":
    unittest.main()

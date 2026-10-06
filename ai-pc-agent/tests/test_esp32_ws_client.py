import asyncio
import json
import unittest

from protocol import TelemetrySample
from sensing.esp32_ws_client import Esp32WsClient


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeWs:
    def __init__(self, fail_after=None):
        self.sent = []
        self.fail_after = fail_after

    async def send(self, text):
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise ConnectionError("gone")
        self.sent.append(json.loads(text))


async def ticking(clock, chunks, step):
    for chunk in chunks:
        yield chunk
        clock.now += step


class SayStreamTests(unittest.TestCase):
    def run_stream(self, ws, chunks, expr, step=0.04):
        client, clock = Esp32WsClient("ws://esp"), FakeClock()
        client._ws = ws
        return asyncio.run(client.say_stream(ticking(clock, chunks, step), expr, clock=clock))

    def test_first_chunk_immediate_then_merged_and_ends_with_done(self):
        ws = FakeWs()
        full = self.run_stream(ws, ["嗯", "…讓", "我", "想想", "看"], "thinking")
        self.assertEqual(full, "嗯…讓我想想看")
        self.assertEqual("".join(m["text"] for m in ws.sent), full)
        self.assertEqual(ws.sent[0], {"t": "say", "text": "嗯", "expr": "thinking", "done": False})
        self.assertTrue(all("expr" not in m for m in ws.sent[1:]))
        self.assertTrue(all(m.get("done") is False for m in ws.sent[:-1]))
        self.assertNotIn("done", ws.sent[-1])
        self.assertLess(len(ws.sent), 5)

    def test_accepts_plain_list(self):
        client, ws = Esp32WsClient("ws://esp"), FakeWs()
        client._ws = ws
        full = asyncio.run(client.say_stream(["哈", "囉"], "neutral", clock=FakeClock()))
        self.assertEqual(full, "哈囉")
        self.assertNotIn("done", ws.sent[-1])

    def test_disconnected_still_returns_full_text_without_raising(self):
        full = self.run_stream(None, ["你", "好"], "neutral")
        self.assertEqual(full, "你好")

    def test_stops_sending_after_failure_but_keeps_reading(self):
        ws = FakeWs(fail_after=1)
        full = self.run_stream(ws, ["一", "二", "三", "四", "五"], "sad", step=0.2)
        self.assertEqual(full, "一二三四五")
        self.assertEqual(len(ws.sent), 1)


class TelemetryGestureTests(unittest.TestCase):
    def test_telemetry_frames_become_touch_events(self):
        received = []
        client = Esp32WsClient("ws://esp", on_event=received.append)
        for t in range(0, 2000, 50):
            fsr = [4000, 4000] if 500 <= t < 1500 else [0, 0]
            client._handle(json.dumps({"schema_version": 1, "type": "telemetry", "uptime_ms": t,
                                       "fsr": {"enabled": True, "raw": fsr}, "imu": {"ok": False}}))
        client._handle('{"t":"touch","kind":"double_tap","strength":1.0,"dur_ms":0}')
        self.assertEqual([e.kind for e in received], ["squeeze", "double_tap"])


    def test_on_telemetry_gets_typed_sample_and_gestures_still_fire(self):
        samples, events = [], []
        client = Esp32WsClient("ws://esp", on_event=events.append, on_telemetry=samples.append)
        for t in range(0, 2000, 50):
            fsr = [4000, 4000] if 500 <= t < 1500 else [0, 0]
            client._handle(json.dumps({"schema_version": 1, "type": "telemetry", "device_id": "dev-1",
                                       "boot_id": "b1", "seq": t, "uptime_ms": t,
                                       "fsr": {"enabled": True, "raw": fsr}, "imu": {"ok": False}}))
        self.assertTrue(all(isinstance(x, TelemetrySample) for x in samples))
        self.assertEqual((samples[0].device_id, samples[0].boot_id), ("dev-1", "b1"))
        self.assertEqual([e.kind for e in events], ["squeeze"])  # 手勢判斷沒被 on_telemetry 影響

    def test_garbage_and_non_telemetry_lines_do_not_call_on_telemetry(self):
        samples = []
        client = Esp32WsClient("ws://esp", on_telemetry=samples.append)
        client._handle("not json at all")
        client._handle('{"t":"hb","uptime_s":3}')
        self.assertEqual(samples, [])


if __name__ == "__main__":
    unittest.main()

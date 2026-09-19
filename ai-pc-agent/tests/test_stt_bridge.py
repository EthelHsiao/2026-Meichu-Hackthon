import asyncio
import json
import unittest

import numpy as np

from sensing.stt import SttBridge


class FakeWs:
    def __init__(self, incoming):
        self.sent = []
        self._incoming = incoming

    async def send(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for msg in self._incoming:
            yield msg


class SttBridgeTests(unittest.TestCase):
    def test_drops_audio_while_disconnected(self):
        bridge = SttBridge("ws://stt")
        bridge.feed_pcm_int16(b"\x00\x01" * 100)
        self.assertTrue(bridge._queue.empty())

    def test_frames_sent_in_order_as_float32_chunks(self):
        async def scenario():
            bridge = SttBridge("ws://stt")
            ws = FakeWs([])
            bridge._ws = ws
            first = np.full(600, 16384, dtype="<i2").tobytes()   # 0.5，跨兩包 512
            second = np.full(10, -32768, dtype="<i2").tobytes()  # -1.0
            bridge.feed_pcm_int16(first)
            bridge.feed_pcm_int16(second)
            task = asyncio.create_task(bridge._send_loop(ws))
            await asyncio.sleep(0.01)
            task.cancel()
            return ws.sent

        sent = asyncio.run(scenario())
        values = np.concatenate([np.frombuffer(p, dtype="<f4") for p in sent])
        self.assertEqual([len(p) // 4 for p in sent], [512, 88, 10])
        self.assertTrue(np.allclose(values[:600], 0.5) and np.allclose(values[600:], -1.0))

    def test_final_text_goes_to_callback(self):
        got = []
        bridge = SttBridge("ws://stt", on_final=got.append)
        ws = FakeWs([json.dumps({"type": "draft", "text": "你"}), "not json",
                     json.dumps({"type": "final", "text": "你好"})])
        asyncio.run(bridge._recv_loop(ws))
        self.assertEqual(got, ["你好"])


if __name__ == "__main__":
    unittest.main()

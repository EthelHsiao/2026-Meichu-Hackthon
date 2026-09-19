"""Local protocol simulation only; these tests don't certify physical sensors."""
import asyncio
import contextlib
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from websockets.server import serve
from websockets.exceptions import ConnectionClosed
from receive_telemetry import receive, validate_sample


def sample(seq=1, boot="test-boot"):
    return {"schema_version": 1, "type": "telemetry", "device_id": "simulated-esp32",
            "boot_id": boot, "seq": seq, "uptime_ms": seq * 50, "sample_period_ms": 50,
            "fsr": {"enabled": True, "raw": [100, 200]},
            "imu": {"ok": True, "status": "ok", "accel_m_s2": [0, 0, 9.81],
                    "gyro_rad_s": [0, 0, 0], "temperature_c": 25}}


class ProtocolTests(unittest.TestCase):
    def test_sensor_failure_is_explicit(self):
        frame = sample()
        frame["imu"] = {"ok": False, "status": "not_found", "accel_m_s2": None,
                        "gyro_rad_s": None, "temperature_c": None}
        self.assertEqual(validate_sample(frame), frame)
        frame["imu"]["accel_m_s2"] = [0, 0, 0]
        with self.assertRaises(ValueError):
            validate_sample(frame)

    def test_reject_corrupt_measurements(self):
        for mutate in (lambda p: p.update(schema_version=2),
                       lambda p: p["fsr"].update(raw=[4096, 2]),
                       lambda p: p["imu"].update(gyro_rad_s=[0, float("nan"), 0]),
                       lambda p: p["imu"].update(accel_m_s2=[0, 0])):
            frame = deepcopy(sample())
            mutate(frame)
            with self.assertRaises(ValueError):
                validate_sample(frame)


class ConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_reconnect_ping_validation_and_recording(self):
        connections = 0
        paths = []
        pings = []

        async def board(ws, path):
            nonlocal connections
            connections += 1
            paths.append(path)
            pings.append(await ws.recv())
            await ws.send('{"schema_version":1,"type":"pong"}')
            if connections == 1:
                await ws.send("invalid JSON")
                for seq in (1, 1, 3):
                    await ws.send(json.dumps(sample(seq)))
                await ws.close()
            else:
                await ws.send(json.dumps(sample(1, "rebooted")))
                try:
                    await ws.wait_closed()
                except ConnectionClosed:
                    pass

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "simulated.jsonl"
            log = io.StringIO()
            async with serve(board, "127.0.0.1", 0) as server:
                port = server.sockets[0].getsockname()[1]
                with contextlib.redirect_stdout(log):
                    count = await receive(f"ws://127.0.0.1:{port}/api/v1/stream", output, duration=3.5)
            records = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(count, 3)
            self.assertEqual([p["sample"]["seq"] for p in records], [1, 3, 1])
            self.assertTrue(all("received_at" in p for p in records))
            self.assertEqual(pings, ["ping", "ping"])
            self.assertEqual(paths, ["/api/v1/stream"] * 2)
            self.assertIn("sequence_gaps=1", log.getvalue())
            self.assertIn("Ignored invalid frame", log.getvalue())

    async def test_duration_limits_silent_connection(self):
        async def silent(ws, path):
            await ws.wait_closed()

        async with serve(silent, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            with contextlib.redirect_stdout(io.StringIO()):
                count = await asyncio.wait_for(receive(f"ws://127.0.0.1:{port}", duration=0.2), 2)
            self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()

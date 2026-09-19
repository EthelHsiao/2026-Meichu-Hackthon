"""Receive real ESP32 telemetry over Wi-Fi; optionally append JSONL on the PC."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time

from websockets.client import connect
from websockets.exceptions import WebSocketException


def validate_sample(sample):
    """Reject incompatible or corrupt frames before saving them as measurements."""
    if not isinstance(sample, dict) or sample.get("type") != "telemetry":
        raise ValueError("expected a telemetry object")
    if type(sample.get("schema_version")) is not int or sample["schema_version"] != 1:
        raise ValueError("expected schema_version 1")
    for key in ("device_id", "boot_id"):
        if not isinstance(sample.get(key), str) or not sample[key]:
            raise ValueError(f"missing {key}")
    for key in ("seq", "uptime_ms", "sample_period_ms"):
        value = sample.get(key)
        if type(value) is not int or value < (1 if key == "sample_period_ms" else 0):
            raise ValueError(f"invalid {key}")
    fsr = sample.get("fsr")
    if not isinstance(fsr, dict) or type(fsr.get("enabled")) is not bool:
        raise ValueError("invalid fsr")
    if fsr["enabled"]:
        raw = fsr.get("raw")
        if not isinstance(raw, list) or len(raw) != 2 or any(type(v) is not int or not 0 <= v <= 4095 for v in raw):
            raise ValueError("FSR raw must contain two 12-bit ADC values")
    elif fsr.get("raw", "missing") is not None:
        raise ValueError("disabled FSR must have raw=null")
    imu = sample.get("imu")
    if not isinstance(imu, dict) or type(imu.get("ok")) is not bool:
        raise ValueError("invalid imu")
    if imu["ok"]:
        if imu.get("status") != "ok":
            raise ValueError("invalid IMU status")
        for key in ("accel_m_s2", "gyro_rad_s"):
            values = imu.get(key)
            if not isinstance(values, list) or len(values) != 3 or not all(type(v) in (int, float) and math.isfinite(v) for v in values):
                raise ValueError(f"invalid {key}")
        value = imu.get("temperature_c")
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("invalid temperature_c")
    else:
        if imu.get("status") not in ("disabled", "not_found", "read_failed"):
            raise ValueError("invalid failed IMU status")
        if any(imu.get(key, "missing") is not None for key in ("accel_m_s2", "gyro_rad_s", "temperature_c")):
            raise ValueError("failed IMU must have null measurements")
    return sample


async def receive(url, output=None, duration=0):
    started = time.monotonic()
    deadline = started + duration if duration else float("inf")
    received = gaps = 0
    previous = None
    last_report = 0
    file = None
    if output:
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        file = output.open("a", encoding="utf-8", buffering=1)
    try:
        while time.monotonic() < deadline:
            try:
                async with asyncio.timeout(None if not duration else max(0.001, deadline - time.monotonic())):
                    async with connect(url, open_timeout=5, close_timeout=1, max_size=8192,
                                       compression=None, ping_interval=20, ping_timeout=10) as ws:
                        print(f"Connected: {url}", flush=True)
                        await ws.send("ping")
                        while time.monotonic() < deadline:
                            raw = await asyncio.wait_for(ws.recv(), timeout=5)
                            try:
                                sample = json.loads(raw)
                                if isinstance(sample, dict) and sample.get("type") == "pong":
                                    print("pong: bidirectional Wi-Fi test passed", flush=True)
                                    continue
                                validate_sample(sample)
                            except (ValueError, TypeError) as exc:
                                print(f"Ignored invalid frame: {exc}", flush=True)
                                continue
                            identity = (sample["device_id"], sample["boot_id"])
                            if previous and previous[0] == identity:
                                delta = (sample["seq"] - previous[1]) & 0xFFFFFFFF
                                if delta == 0:
                                    continue  # reconnect can replay the cached sample
                                if delta < 0x80000000:
                                    gaps += delta - 1
                                else:
                                    print("Ignored out-of-order sequence", flush=True)
                                    continue
                            previous = (identity, sample["seq"])
                            received += 1
                            record = {"received_at": datetime.now(timezone.utc).isoformat(), "sample": sample}
                            if file:
                                file.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                            now = time.monotonic()
                            if now - last_report >= 1:
                                last_report = now
                                print(f"seq={sample['seq']} fsr={sample['fsr']['raw']} "
                                      f"imu={sample['imu']['status']} accel={sample['imu']['accel_m_s2']} "
                                      f"received={received} gaps={gaps}", flush=True)
            except (OSError, TimeoutError, WebSocketException) as exc:
                if time.monotonic() >= deadline:
                    break
                print(f"Disconnected / no data: {exc}; retry in 2 s", flush=True)
                await asyncio.sleep(min(2, max(0, deadline - time.monotonic())))
    finally:
        if file:
            file.close()
        print(f"Stopped: received={received}, sequence_gaps={gaps}", flush=True)
    return received


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="ws://192.168.4.1:81/api/v1/stream")
    parser.add_argument("--output", help="Append received samples to a JSONL file")
    parser.add_argument("--duration", type=float, default=0, help="Seconds to run; 0 means until Ctrl+C")
    args = parser.parse_args()
    if not math.isfinite(args.duration) or args.duration < 0:
        parser.error("--duration must be finite and nonnegative")
    if not args.url.startswith(("ws://", "wss://")):
        parser.error("--url must start with ws:// or wss://")
    try:
        count = asyncio.run(receive(args.url, args.output, args.duration))
    except KeyboardInterrupt:
        return
    if args.duration and count == 0:
        raise SystemExit("No valid telemetry received; check Wi-Fi, board IP, and Stage 9 firmware.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import numpy as np
import sounddevice as sd
import websockets

TARGET_SAMPLE_RATE = 16_000
PACKET_SAMPLES = 512


def print_event(message: dict[str, Any]) -> None:
    message_type = message.get("type")
    if message_type == "ready":
        print(f"\nready: device={message.get('device')}", flush=True)
    elif message_type == "draft":
        text = message.get("text") or "..."
        print(f"\rdraft: {text:<100}", end="", flush=True)
    elif message_type == "final":
        text = message.get("text") or "(no speech recognized)"
        print(f"\nfinal: {text}", flush=True)
        print(
            f"       decode={message.get('latency_ms')} ms "
            f"rtf={message.get('real_time_factor')}",
            flush=True,
        )
    elif message_type == "vad":
        print(f"\nvad: {message.get('state')}", flush=True)
    elif message_type == "asr_error":
        print(f"\nasr error: {message}", file=sys.stderr, flush=True)
    elif message_type == "session_stats":
        print(
            "\nsession: "
            f"duration={message.get('session_seconds')}s "
            f"max_gpu_busy={message.get('max_gpu_busy_percent')}% "
            f"max_gpu_memory={message.get('max_gpu_memory_bytes')} bytes",
            flush=True,
        )


async def run(ws_url: str, input_device: int | None) -> None:
    loop = asyncio.get_running_loop()
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=32)
    stopped = asyncio.Event()

    def enqueue_audio(packet: bytes) -> None:
        try:
            audio_queue.put_nowait(packet)
        except asyncio.QueueFull:
            print("audio queue full; dropping packet", file=sys.stderr, flush=True)

    def audio_callback(indata: np.ndarray, frames: int, callback_time: Any, status: Any) -> None:
        if status:
            print(f"audio: {status}", file=sys.stderr, flush=True)
        packet = np.asarray(indata[:, 0], dtype=np.float32).tobytes()
        loop.call_soon_threadsafe(enqueue_audio, packet)

    async with websockets.connect(ws_url, max_size=None) as websocket:
        await websocket.send(json.dumps({
            "type": "start",
            "sampleRate": TARGET_SAMPLE_RATE,
            "channels": 1,
            "encoding": "float32",
        }))

        async def receive_messages() -> None:
            try:
                async for raw_message in websocket:
                    print_event(json.loads(raw_message))
            except websockets.ConnectionClosed:
                pass
            finally:
                stopped.set()

        receiver = asyncio.create_task(receive_messages())
        try:
            print("Speak Mandarin or Mandarin-English. Press Ctrl-C to stop.", flush=True)
            with sd.InputStream(
                samplerate=TARGET_SAMPLE_RATE,
                blocksize=PACKET_SAMPLES,
                channels=1,
                dtype="float32",
                device=input_device,
                callback=audio_callback,
            ):
                while not stopped.is_set():
                    packet = await audio_queue.get()
                    await websocket.send(packet)
        except KeyboardInterrupt:
            print("\nstopping...", flush=True)
        finally:
            if websocket.state.name == "OPEN":
                await websocket.send(json.dumps({"type": "stop"}))
            try:
                await asyncio.wait_for(receiver, timeout=10)
            except asyncio.TimeoutError:
                receiver.cancel()


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream the local microphone to Breeze STT and print text.")
    parser.add_argument("--ws", default="ws://127.0.0.1:8765/ws/audio", help="Breeze backend WebSocket URL")
    parser.add_argument("--device", type=int, help="sounddevice input device index")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.ws, args.device))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"microphone client failed: {exc}", file=sys.stderr)
        print("Run `python -m sounddevice` to list available input devices.", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

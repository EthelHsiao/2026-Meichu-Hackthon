from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import wave
from pathlib import Path
from typing import Sequence

import numpy as np

try:
    from . import main
except ImportError:  # pragma: no cover - supports direct test execution
    import main  # type: ignore[no-redef]


def existing_wav(value: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"WAV file does not exist: {path}")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark warmed Breeze STT decoding")
    parser.add_argument("input", type=existing_wav, help="mono PCM WAV input")
    parser.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda", "rocm"))
    parser.add_argument("--runs", type=int, default=3)
    return parser


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav_file:
        if wav_file.getnchannels() != 1 or wav_file.getsampwidth() != 2:
            raise ValueError("benchmark input must be mono 16-bit PCM WAV")
        frames = wav_file.readframes(wav_file.getnframes())
        return np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0


def summarize_latencies(latencies: Sequence[float], audio_seconds: float) -> dict[str, object]:
    values = list(latencies)
    median = statistics.median(values) * 1000 if values else None
    p95 = float(np.percentile(values, 95)) * 1000 if values else None
    rtf = (statistics.median(values) / audio_seconds) if values and audio_seconds > 0 else None
    return {
        "runs": len(values),
        "median_latency_ms": round(median, 2) if median is not None else None,
        "p95_latency_ms": round(p95, 2) if p95 is not None else None,
        "real_time_factor": round(rtf, 4) if rtf is not None else None,
    }


async def run_benchmark(path: Path, device: str, runs: int) -> dict[str, object]:
    if runs < 1:
        raise ValueError("--runs must be at least 1")
    audio = read_wav(path)
    main.ASR_DEVICE = device
    runtime = await main.load_runtime()
    if audio.size:
        await main.transcribe(runtime, audio)  # warm model and allocator
    latencies: list[float] = []
    for _ in range(runs):
        if not audio.size:
            break
        _, latency = await main.transcribe(runtime, audio)
        latencies.append(latency)
    result = summarize_latencies(latencies, audio.size / main.SAMPLE_RATE)
    result.update({"device": str(runtime.device), "dtype": str(runtime.dtype)})
    return result


def main_cli() -> None:
    args = build_parser().parse_args()
    result = asyncio.run(run_benchmark(args.input, args.device, args.runs))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main_cli()

from __future__ import annotations

import asyncio
import glob
import json
import logging
import os
import time
import wave
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

SAMPLE_RATE = 16_000
PACKET_SAMPLES = 512
MIN_SPEECH_SECONDS = 0.35
END_SILENCE_SECONDS = float(os.getenv("END_SILENCE_SECONDS", "1.0"))
PRE_ROLL_SECONDS = 0.35
DRAFT_WINDOW_SECONDS = float(os.getenv("DRAFT_WINDOW_SECONDS", "4.0"))
DRAFT_INTERVAL_SECONDS = float(os.getenv("DRAFT_INTERVAL_SECONDS", "0.75"))
SPEECH_RMS_THRESHOLD = float(os.getenv("SPEECH_RMS_THRESHOLD", "0.012"))
SPEECH_START_RMS_THRESHOLD = float(
    os.getenv("SPEECH_START_RMS_THRESHOLD", str(max(SPEECH_RMS_THRESHOLD, 0.06)))
)
SPEECH_CONTINUE_RMS_THRESHOLD = float(
    os.getenv("SPEECH_CONTINUE_RMS_THRESHOLD", str(min(SPEECH_RMS_THRESHOLD, SPEECH_START_RMS_THRESHOLD)))
)
VAD_START_CHUNKS = int(os.getenv("VAD_START_CHUNKS", "3"))
MODEL_ID = os.getenv("BREEZE_MODEL", "MediaTek-Research/Breeze-ASR-25")
ASR_DEVICE = os.getenv("ASR_DEVICE", "auto").strip().lower()
CPU_THREADS = int(os.getenv("STT_CPU_THREADS", "8"))
CPU_BF16 = os.getenv("STT_CPU_BF16", "auto").strip().lower()
MAX_NEW_TOKENS = int(os.getenv("STT_MAX_NEW_TOKENS", "128"))
SEGMENT_DIR = Path(__file__).resolve().parent / "segments"
SEGMENT_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("local-stt")
app = FastAPI(title="Local Breeze STT")


@dataclass
class Runtime:
    processor: Any
    model: Any
    device: Any
    dtype: Any
    load_seconds: float


@dataclass
class VadGate:
    start_threshold: float
    continue_threshold: float
    start_chunks: int
    end_silence_samples: int
    in_speech: bool = False
    consecutive_speech_chunks: int = 0
    silent_samples: int = 0

    def update(self, rms: float, sample_count: int) -> tuple[bool, bool]:
        """Return (started, ended), requiring stable speech and silence hangover."""
        if not self.in_speech:
            if rms >= self.start_threshold:
                self.consecutive_speech_chunks += 1
            else:
                self.consecutive_speech_chunks = 0
            if self.consecutive_speech_chunks < max(1, self.start_chunks):
                return False, False
            self.in_speech = True
            self.consecutive_speech_chunks = 0
            self.silent_samples = 0
            return True, False

        if rms >= self.continue_threshold:
            self.silent_samples = 0
            return False, False
        self.silent_samples += sample_count
        if self.silent_samples < self.end_silence_samples:
            return False, False
        return False, True

    def reset(self) -> None:
        self.in_speech = False
        self.consecutive_speech_chunks = 0
        self.silent_samples = 0


@dataclass
class GpuSessionMonitor:
    """Track peak AMD GPU busy percentage and allocated memory for one session."""

    busy_paths: tuple[Path, ...] = field(
        default_factory=lambda: tuple(Path(path) for path in glob.glob(
            "/sys/class/drm/card*/device/gpu_busy_percent"
        ))
    )
    memory_paths: tuple[Path, ...] = field(
        default_factory=lambda: tuple(Path(path) for path in glob.glob(
            "/sys/class/drm/card*/device/mem_info_vram_used"
        ))
    )
    max_busy_percent: float | None = None
    max_memory_bytes: int | None = None

    def record(self, busy_percent: float | None = None, vram_bytes: int | None = None) -> None:
        if busy_percent is not None:
            self.max_busy_percent = max(self.max_busy_percent or 0.0, busy_percent)
        if vram_bytes is not None:
            self.max_memory_bytes = max(self.max_memory_bytes or 0, vram_bytes)

    def sample(self) -> None:
        for path in self.busy_paths:
            try:
                self.record(busy_percent=float(path.read_text().strip()))
            except (OSError, ValueError):
                continue
        for path in self.memory_paths:
            try:
                self.record(vram_bytes=int(path.read_text().strip()))
            except (OSError, ValueError):
                continue

    def snapshot(self, torch: Any | None = None, device: Any | None = None) -> dict[str, Any]:
        if torch is not None and device is not None and getattr(device, "type", None) == "cuda":
            try:
                self.record(vram_bytes=int(torch.cuda.max_memory_allocated(device)))
            except (AttributeError, RuntimeError):
                pass
        return {
            "max_gpu_busy_percent": self.max_busy_percent,
            "max_gpu_memory_bytes": self.max_memory_bytes,
            "gpu_busy_monitor_available": bool(self.busy_paths),
        }


_runtime: Runtime | None = None
_runtime_lock = asyncio.Lock()


def validate_accelerator(torch: Any, device: Any, requested_mode: str) -> None:
    """Validate an explicit accelerator request before model loading."""
    if device.type == "cpu":
        return
    if requested_mode == "rocm" and not getattr(torch.version, "hip", None):
        raise RuntimeError(
            "ASR_DEVICE='rocm' requires a ROCm/HIP PyTorch build; detected "
            f"torch CUDA={getattr(torch.version, 'cuda', None)!r}, HIP=None. "
            "Install backend/requirements.rocm.txt and run check_env.py."
        )
    if not torch.cuda.is_available():
        raise RuntimeError(
            f"ASR_DEVICE={requested_mode!r} requested an accelerator, but no "
            "PyTorch device is available; detected "
            f"torch CUDA={getattr(torch.version, 'cuda', None)!r}, "
            f"HIP={getattr(torch.version, 'hip', None)!r}. Install a compatible "
            "ROCm/CUDA torch build and verify it with `python backend/check_env.py`."
        )


def resolve_device(torch: Any, requested_mode: str | None = None) -> Any:
    mode = (ASR_DEVICE if requested_mode is None else requested_mode).strip().lower()
    if mode in {"", "auto"}:
        return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    if mode == "rocm":
        device = torch.device("cuda:0")
        validate_accelerator(torch, device, mode)
        return device
    if mode == "cuda":
        device = torch.device("cuda:0")
        validate_accelerator(torch, device, mode)
        return device
    return torch.device(mode)


def draft_deadline_after_decode(completed_at: float, latency: float, interval: float) -> float:
    """Prevent draft work from being scheduled faster than decoding can finish."""
    return completed_at + max(interval, latency)


def torch_diagnostics(torch: Any, setting: str) -> dict[str, Any]:
    hip = getattr(torch.version, "hip", None)
    cuda_build = getattr(torch.version, "cuda", None)
    available = bool(torch.cuda.is_available())
    if hip:
        accelerator = "rocm"
    elif cuda_build:
        accelerator = "cuda"
    else:
        accelerator = "cpu"
    return {
        "torch": getattr(torch, "__version__", None),
        "torch_cuda_available": available,
        "torch_device": torch.cuda.get_device_name(0) if available else None,
        "torch_hip": hip,
        "torch_cuda_build": cuda_build,
        "accelerator": accelerator,
        "asr_device_setting": setting,
        "cpu_threads_setting": CPU_THREADS,
        "cpu_bf16_setting": CPU_BF16,
        "max_new_tokens": MAX_NEW_TOKENS,
    }


async def monitor_gpu(monitor: GpuSessionMonitor, stop: asyncio.Event) -> None:
    while not stop.is_set():
        monitor.sample()
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.25)
        except asyncio.TimeoutError:
            continue


async def load_runtime() -> Runtime:
    global _runtime
    if _runtime is not None:
        return _runtime
    async with _runtime_lock:
        if _runtime is not None:
            return _runtime
        started = time.perf_counter()
        try:
            import torch
            from transformers import WhisperForConditionalGeneration, WhisperProcessor
        except ImportError as exc:
            raise RuntimeError(
                "Install backend requirements before starting ASR: " + str(exc)
            ) from exc

        if CPU_THREADS > 0:
            torch.set_num_threads(CPU_THREADS)
        device = resolve_device(torch, ASR_DEVICE)
        use_cpu_bf16 = (
            device.type == "cpu"
            and CPU_BF16 in {"", "auto", "1", "true", "yes", "on"}
            and hasattr(torch.cpu, "_is_avx512_bf16_supported")
            and torch.cpu._is_avx512_bf16_supported()
        )
        dtype = torch.float16 if device.type == "cuda" else torch.bfloat16 if use_cpu_bf16 else torch.float32
        logger.info(
            "Loading %s on %s (torch HIP=%s CUDA=%s)",
            MODEL_ID,
            device,
            getattr(torch.version, "hip", None),
            getattr(torch.version, "cuda", None),
        )
        processor = await asyncio.to_thread(WhisperProcessor.from_pretrained, MODEL_ID)
        model = await asyncio.to_thread(
            WhisperForConditionalGeneration.from_pretrained,
            MODEL_ID,
            torch_dtype=dtype,
        )
        model = model.to(device).eval()
        _runtime = Runtime(processor, model, device, dtype, time.perf_counter() - started)
        logger.info("Breeze loaded in %.2fs", _runtime.load_seconds)
        return _runtime


def decode_audio(runtime: Runtime, audio: np.ndarray) -> str:
    import torch

    inputs = runtime.processor(
        audio,
        sampling_rate=SAMPLE_RATE,
        return_tensors="pt",
        return_attention_mask=True,
    )
    input_features = inputs.input_features.to(runtime.device, dtype=runtime.dtype)
    generate_kwargs: dict[str, Any] = {
        "input_features": input_features,
        "max_new_tokens": MAX_NEW_TOKENS,
        "num_beams": 1,
        "do_sample": False,
        "use_cache": True,
    }
    if hasattr(inputs, "attention_mask"):
        generate_kwargs["attention_mask"] = inputs.attention_mask.to(runtime.device)
    generate_kwargs["forced_decoder_ids"] = runtime.processor.get_decoder_prompt_ids(
        language="zh", task="transcribe", no_timestamps=True
    )
    with torch.inference_mode():
        generated = runtime.model.generate(**generate_kwargs)
    text = runtime.processor.batch_decode(generated, skip_special_tokens=True)[0]
    return " ".join(text.strip().split())


async def transcribe(runtime: Runtime, audio: np.ndarray) -> tuple[str, float]:
    started = time.perf_counter()
    text = await asyncio.to_thread(decode_audio, runtime, audio)
    return text, time.perf_counter() - started


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    if _runtime is None:
        return {"status": "ok", "model_loaded": False}
    import torch

    return {
        "status": "ok",
        "model_loaded": True,
        "device": str(_runtime.device),
        "dtype": str(_runtime.dtype),
        "cpu_threads": torch.get_num_threads() if _runtime.device.type == "cpu" else None,
        "model_load_seconds": round(_runtime.load_seconds, 3),
    }


@app.get("/diagnostics")
async def diagnostics() -> dict[str, Any]:
    try:
        import torch

        return torch_diagnostics(torch, ASR_DEVICE)
    except ImportError:
        return {"torch": None, "asr_device_setting": ASR_DEVICE}


async def send(websocket: WebSocket, payload: dict[str, Any]) -> None:
    await websocket.send_text(json.dumps(payload, ensure_ascii=False))


@app.websocket("/ws/audio")
async def audio_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        runtime = await load_runtime()
    except Exception as exc:
        logger.exception("Unable to load Breeze ASR")
        await send(websocket, {"type": "asr_error", "stage": "model_load", "error": str(exc)})
        await websocket.close(code=1011)
        return
    session_started_at = time.perf_counter()
    gpu_monitor = GpuSessionMonitor()
    gpu_monitor_stop = asyncio.Event()
    gpu_monitor_task = asyncio.create_task(monitor_gpu(gpu_monitor, gpu_monitor_stop))
    packet_buffer: deque[np.ndarray] = deque()
    pre_roll: deque[np.ndarray] = deque(maxlen=max(1, int(PRE_ROLL_SECONDS * SAMPLE_RATE / PACKET_SAMPLES)))
    speech_audio: list[np.ndarray] = []
    vad_gate = VadGate(
        start_threshold=SPEECH_START_RMS_THRESHOLD,
        continue_threshold=SPEECH_CONTINUE_RMS_THRESHOLD,
        start_chunks=VAD_START_CHUNKS,
        end_silence_samples=int(END_SILENCE_SECONDS * SAMPLE_RATE),
    )
    in_speech = False
    last_draft_samples = 0
    draft_blocked_until = 0.0
    segment_started_at = 0.0
    packet_count = 0
    sample_count = 0
    last_level_report = 0.0
    vad_state = "silence"
    try:
        await send(websocket, {"type": "ready", "device": str(runtime.device)})
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            if message.get("text"):
                if json.loads(message["text"]).get("type") == "stop":
                    break
                continue
            raw = message.get("bytes")
            if not raw:
                continue
            packet = np.frombuffer(raw, dtype=np.float32)
            if packet.size == 0:
                continue
            packet_count += 1
            sample_count += packet.size
            packet_buffer.append(packet)
            while packet_buffer:
                chunk = packet_buffer.popleft()
                rms = float(np.sqrt(np.mean(np.square(chunk), dtype=np.float64)))
                peak = float(np.max(np.abs(chunk)))
                started, ended = vad_gate.update(rms, chunk.size)
                now = time.perf_counter()
                if now - last_level_report >= 0.5:
                    await send(websocket, {
                        "type": "audio_level",
                        "rms": round(rms, 5),
                        "peak": round(peak, 5),
                        "packets": packet_count,
                        "audio_seconds": round(sample_count / SAMPLE_RATE, 2),
                        "vad": vad_state,
                    })
                    last_level_report = now
                if not in_speech:
                    pre_roll.append(chunk)
                    if started:
                        in_speech = True
                        segment_started_at = time.perf_counter()
                        speech_audio.extend(pre_roll)
                        pre_roll.clear()
                        vad_state = "speech"
                        await send(websocket, {"type": "vad", "state": "speech"})
                else:
                    speech_audio.append(chunk)

                    current = np.concatenate(speech_audio)
                    enough_for_draft = current.size >= int(MIN_SPEECH_SECONDS * SAMPLE_RATE)
                    interval_elapsed = current.size - last_draft_samples >= int(DRAFT_INTERVAL_SECONDS * SAMPLE_RATE)
                    if enough_for_draft and interval_elapsed and time.perf_counter() >= draft_blocked_until:
                        draft_audio = current[-int(DRAFT_WINDOW_SECONDS * SAMPLE_RATE) :]
                        text, latency = await transcribe(runtime, draft_audio)
                        last_draft_samples = current.size
                        draft_blocked_until = draft_deadline_after_decode(
                            time.perf_counter(), latency, DRAFT_INTERVAL_SECONDS
                        )
                        await send(websocket, {
                            "type": "draft",
                            "text": text,
                            "latency_ms": round(latency * 1000, 1),
                            "audio_seconds": round(current.size / SAMPLE_RATE, 2),
                        })

                    if ended:
                        await finalize_segment(websocket, runtime, speech_audio, segment_started_at)
                        in_speech = False
                        last_draft_samples = 0
                        draft_blocked_until = 0.0
                        speech_audio = []
                        pre_roll.clear()
                        vad_gate.reset()
                        vad_state = "silence"
                        await send(websocket, {"type": "vad", "state": "silence"})
    except WebSocketDisconnect:
        logger.info("Audio client disconnected")
    finally:
        gpu_monitor_stop.set()
        await gpu_monitor_task
        gpu_monitor.sample()
        if in_speech and speech_audio:
            try:
                await finalize_segment(websocket, runtime, speech_audio, segment_started_at)
            except (WebSocketDisconnect, RuntimeError):
                logger.info("Client disconnected before final transcript")
        try:
            import torch

            session_stats = {
                "type": "session_stats",
                "session_seconds": round(time.perf_counter() - session_started_at, 3),
                **gpu_monitor.snapshot(torch, runtime.device),
            }
        except ImportError:
            session_stats = {
                "type": "session_stats",
                "session_seconds": round(time.perf_counter() - session_started_at, 3),
                **gpu_monitor.snapshot(),
            }
        logger.info("session_stats=%s", session_stats)
        try:
            await send(websocket, session_stats)
        except (WebSocketDisconnect, RuntimeError):
            pass


async def finalize_segment(
    websocket: WebSocket, runtime: Runtime, chunks: list[np.ndarray], started_at: float
) -> None:
    audio = np.concatenate(chunks).astype(np.float32, copy=False)
    if audio.size < int(MIN_SPEECH_SECONDS * SAMPLE_RATE):
        logger.info("discarding short VAD segment=%.2fs", audio.size / SAMPLE_RATE)
        return
    segment_name = f"{int(time.time() * 1000)}.wav"
    segment_path = SEGMENT_DIR / segment_name
    pcm16 = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm16 * 32767.0).astype("<i2", copy=False)
    with wave.open(str(segment_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm16.tobytes())
    text, latency = await transcribe(runtime, audio)
    elapsed = time.perf_counter() - started_at
    await send(websocket, {
        "type": "final",
        "text": text,
        "latency_ms": round(latency * 1000, 1),
        "end_to_final_ms": round(latency * 1000, 1),
        "segment_seconds": round(audio.size / SAMPLE_RATE, 2),
        "real_time_factor": round(latency / max(audio.size / SAMPLE_RATE, 0.001), 3),
        "wall_seconds": round(elapsed, 3),
        "audio_url": f"/segments/{segment_name}",
    })
    logger.info("final segment=%.2fs latency=%.2fs text=%s", audio.size / SAMPLE_RATE, latency, text)


app.mount(
    "/segments",
    StaticFiles(directory=SEGMENT_DIR),
    name="segments",
)
app.mount(
    "/",
    StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend", html=True),
    name="frontend",
)

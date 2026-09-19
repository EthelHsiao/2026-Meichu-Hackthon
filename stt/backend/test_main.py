from __future__ import annotations

import types
import tempfile
import wave

import unittest

from main import resolve_device


def fake_torch(*, hip: str | None = None, cuda: str | None = None, available: bool):
    class FakeCuda:
        @staticmethod
        def is_available() -> bool:
            return available

    class FakeDevice:
        def __init__(self, name: str):
            self.type = name.split(":", 1)[0]
            self.name = name

        def __str__(self) -> str:
            return self.name

    return types.SimpleNamespace(
        version=types.SimpleNamespace(hip=hip, cuda=cuda),
        cuda=FakeCuda(),
        device=FakeDevice,
    )


def fake_diagnostics_torch(*, hip: str | None, cuda: str | None, available: bool):
    torch = fake_torch(hip=hip, cuda=cuda, available=available)

    class GuardedCuda:
        @staticmethod
        def is_available() -> bool:
            return available

        @staticmethod
        def get_device_name(index: int) -> str:
            if not available:
                raise AssertionError("get_device_name called while unavailable")
            return "AMD Radeon Test GPU"

    torch.cuda = GuardedCuda()
    torch.__version__ = "test"
    return torch


class DeviceResolutionTests(unittest.TestCase):
    def test_rocm_requires_hip_and_selects_cuda_zero(self):
        torch = fake_torch(hip="6.4", available=True)
        self.assertEqual(str(resolve_device(torch, "rocm")), "cuda:0")


    def test_rocm_rejects_cuda_only_build(self):
        torch = fake_torch(hip=None, cuda="13.0", available=True)
        with self.assertRaisesRegex(RuntimeError, "ROCm/HIP"):
            resolve_device(torch, "rocm")


    def test_auto_uses_cpu_without_accelerator(self):
        torch = fake_torch(hip=None, cuda=None, available=False)
        self.assertEqual(str(resolve_device(torch, "auto")), "cpu")


    def test_rocm_rejects_unavailable_device(self):
        torch = fake_torch(hip="6.4", available=False)
        with self.assertRaisesRegex(RuntimeError, "available"):
            resolve_device(torch, "rocm")

    def test_rocm_unavailable_error_reports_non_hip_build(self):
        torch = fake_torch(hip=None, cuda="13.0", available=False)
        with self.assertRaisesRegex(RuntimeError, "CUDA='13.0'.*HIP=None"):
            resolve_device(torch, "rocm")

    def test_diagnostics_does_not_probe_unavailable_device(self):
        from main import torch_diagnostics

        result = torch_diagnostics(
            fake_diagnostics_torch(hip=None, cuda=None, available=False), "auto"
        )
        self.assertIsNone(result["torch_device"])

    def test_diagnostics_classifies_hip(self):
        from main import torch_diagnostics

        result = torch_diagnostics(
            fake_diagnostics_torch(hip="6.4", cuda=None, available=True), "rocm"
        )
        self.assertEqual(result["accelerator"], "rocm")

    def test_percentile_and_rtf_handle_zero_length_audio(self):
        from benchmark import summarize_latencies

        result = summarize_latencies([], audio_seconds=0.0)
        self.assertEqual(result["runs"], 0)
        self.assertIsNone(result["real_time_factor"])

    def test_benchmark_parser_requires_existing_wav(self):
        from benchmark import build_parser

        with self.assertRaises(SystemExit):
            build_parser().parse_args(["/tmp/missing-stt-input.wav"])

    def test_read_wav_resamples_48khz_to_service_rate(self):
        from benchmark import read_wav

        with tempfile.NamedTemporaryFile(suffix=".wav") as handle:
            with wave.open(handle.name, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(48_000)
                wav_file.writeframes(b"\x00\x00" * 48_000)
            audio = read_wav(__import__("pathlib").Path(handle.name))
        self.assertEqual(audio.size, 16_000)

    def test_vad_requires_consecutive_chunks_to_start(self):
        from main import VadGate

        gate = VadGate(start_threshold=0.06, continue_threshold=0.04, start_chunks=3,
                       end_silence_samples=1024)
        self.assertEqual(gate.update(0.08, 512), (False, False))
        self.assertEqual(gate.update(0.01, 512), (False, False))
        self.assertEqual(gate.update(0.08, 512), (False, False))
        self.assertEqual(gate.update(0.08, 512), (False, False))
        self.assertEqual(gate.update(0.08, 512), (True, False))

    def test_vad_ends_only_after_hangover_silence(self):
        from main import VadGate

        gate = VadGate(start_threshold=0.06, continue_threshold=0.04, start_chunks=1,
                       end_silence_samples=1024)
        self.assertEqual(gate.update(0.08, 512), (True, False))
        self.assertEqual(gate.update(0.03, 512), (False, False))
        self.assertEqual(gate.update(0.01, 512), (False, True))

    def test_draft_deadline_accounts_for_decode_latency(self):
        from main import draft_deadline_after_decode

        self.assertEqual(draft_deadline_after_decode(10.0, 2.0, 0.75), 12.0)
        self.assertEqual(draft_deadline_after_decode(10.0, 0.2, 0.75), 10.75)

    def test_gpu_session_monitor_keeps_peak_values(self):
        from main import GpuSessionMonitor

        monitor = GpuSessionMonitor()
        monitor.record(busy_percent=12.5, vram_bytes=100)
        monitor.record(busy_percent=87.0, vram_bytes=50)
        self.assertEqual(monitor.snapshot()["max_gpu_busy_percent"], 87.0)
        self.assertEqual(monitor.snapshot()["max_gpu_memory_bytes"], 100)


if __name__ == "__main__":
    unittest.main()

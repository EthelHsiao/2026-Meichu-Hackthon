from __future__ import annotations

import types

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


if __name__ == "__main__":
    unittest.main()

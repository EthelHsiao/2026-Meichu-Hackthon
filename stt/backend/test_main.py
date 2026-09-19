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


if __name__ == "__main__":
    unittest.main()

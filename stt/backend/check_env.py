from __future__ import annotations

import importlib.util
import platform
import sys

print('python:', sys.executable)
print('platform:', platform.platform())
if importlib.util.find_spec('torch') is None:
    print('torch: not installed')
    raise SystemExit(0)

import torch

print('torch:', torch.__version__)
print('torch.cuda.is_available:', torch.cuda.is_available())
print('torch.cuda.device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)
print('torch.version.hip:', getattr(torch.version, 'hip', None))
print('torch.version.cuda:', getattr(torch.version, 'cuda', None))
print('classification:', 'AMD ROCm/HIP' if getattr(torch.version, 'hip', None) else 'NVIDIA CUDA' if getattr(torch.version, 'cuda', None) else 'CPU-only or unknown')

# Low-latency ROCm STT design

## Goal

Minimize end-to-end transcription latency for one live microphone stream on
the AMD Ryzen AI 7 350/Radeon GPU. Preserve the existing local Breeze-ASR-25
service and its CPU fallback. This work does not add an NPU backend: PyTorch
Whisper inference uses the Radeon GPU through ROCm, while NPU support would
require a separate runtime and needs a separate benchmark before it can be
claimed faster.

## Architecture

The service will treat `ASR_DEVICE=rocm` as an explicit AMD GPU request and
map it to PyTorch's `cuda:0` device. This is the correct PyTorch API for both
CUDA and ROCm builds. `ASR_DEVICE=auto` will select the GPU only when the
installed torch build exposes HIP and reports a usable accelerator; otherwise
it will use CPU. `ASR_DEVICE=cpu` remains an explicit fallback.

An explicit ROCm request must fail before model loading when torch is not a
ROCm/HIP build or no device is available. The error must identify the detected
torch build and explain how to run the existing environment check. This avoids
the current risk of a misleading CPU fallback when GPU latency is expected.

The already-long-lived runtime continues to load the processor and model once
per service process. GPU execution uses `float16`; CPU retains the existing
BF16/FP32 selection. Audio stays as Float32 until the processor creates input
features, so the live WebSocket path has no new audio encoding or copy stage.

## Latency behavior

Draft transcription remains a bounded sliding window. Its defaults will favor
responsiveness for one speaker: a smaller draft window and shorter draft
interval, while final transcription still decodes the complete VAD segment.
The settings remain environment variables so accuracy/latency tradeoffs can be
adjusted without changing code.

The server will report selected device, accelerator classification, dtype,
model load time, and per-decode latency. A small command-line benchmark will
accept a WAV input, warm the runtime, execute repeated decodes, and emit
machine-readable latency/real-time-factor results. It will be used to compare
CPU and ROCm modes using the same audio.

## Error handling

- `rocm` without a ROCm torch build or available GPU: fail with a clear setup
  error; do not silently run on CPU.
- `cuda` remains supported for users intentionally using the raw PyTorch name;
  it validates an available accelerator before loading.
- `auto` remains resilient: it selects CPU when no compatible GPU runtime is
  installed.
- Diagnostics never call `get_device_name` unless an accelerator is available.

## Testing and verification

Unit tests will inject a minimal fake torch module to cover CPU selection,
ROCm auto selection, explicit `rocm` selection, and clear failures for absent
HIP/device support. The benchmark's argument validation and output shape will
also be tested without loading a model.

Verification has two layers:

1. Run the Python test suite in the service environment.
2. On a correctly installed ROCm host, run `check_env`, then the WAV benchmark
   in `ASR_DEVICE=cpu` and `ASR_DEVICE=rocm`; retain its reported median
   latency and real-time factor as the performance comparison.

## Non-goals

- Installing system ROCm packages, changing Linux groups, or rebooting the
  machine.
- NPU/XDNA execution-provider integration.
- Changing the model, VAD algorithm, WebSocket protocol, or cloud behavior.

# Local Breeze-ASR-25 STT prototype

This is a local real-time speech-to-text prototype for Taiwanese Mandarin with Mandarin-English code switching. The browser captures microphone audio, resamples it to mono 16 kHz, and sends continuous Float32 PCM packets over a WebSocket. The backend uses VAD boundaries and sliding-window Breeze-ASR-25 decodes; it does not create fixed five-second WAV files and it has no cloud STT, RAG, or transcript refinement.

## Current machine finding

On this Ubuntu 24.04.4 host with kernel `7.0.0-28-generic`, the Radeon display controller is bound to `amdgpu`, and `/dev/kfd` plus `/dev/dri/renderD128` exist. `rocminfo` and `amd-smi` are not installed. System Python has no PyTorch, so `torch.cuda` has not yet been testable here. The first implementation therefore supports CPU immediately and keeps the PyTorch device path ROCm-compatible.

Do not interpret `torch.cuda` as NVIDIA-only: a ROCm PyTorch build intentionally reports AMD through that API. After installing a compatible ROCm torch wheel, run:

```bash
python -m stt.backend.check_env
```

and compare `torch.version.hip`, `torch.version.cuda`, `torch.cuda.is_available()`, and the device name. Do not install a system ROCm stack or modify kernel drivers as part of this prototype.

## Run the CPU baseline

Create an environment outside the system Python, then install the dependencies. PyTorch installation is hardware-specific; use the official ROCm wheel for AMD or a CPU wheel for the baseline.

On Ubuntu, install the venv and microphone runtime prerequisites once:

```bash
sudo apt install python3.12-venv libportaudio2
```

```bash
cd stt
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
# Install the appropriate torch/torchaudio build first.
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765/` in a browser. The backend serves the bundled frontend and WebSocket from the same origin.

For a terminal-only microphone test, install the backend requirements and run a second terminal command:

```bash
.venv/bin/python -m backend.mic_stdout
```

Speak after the client prints `ready`. Draft text updates on the current terminal line; finalized segments are printed on their own lines. Stop with `Ctrl-C`. To inspect or select an input device:

```bash
.venv/bin/python -m sounddevice
.venv/bin/python -m backend.mic_stdout --device 2
```

On Ubuntu, `sounddevice` may require the PortAudio runtime. If microphone opening fails, install the distribution package with `sudo apt install libportaudio2` and retry. The CLI client does not run ASR itself; it streams audio to the same local Breeze backend as the browser.

The first model request downloads `MediaTek-Research/Breeze-ASR-25` into the local Hugging Face cache. No API key or external transcription service is used. Microphone permission is required.

## ROCm GPU test for this machine

The AMD workshop slides explicitly target this machine as Ryzen AI 7 350 / `gfx1152` and link AMD's ROCm installation page for Ubuntu 24.04.4. The current `.venv` contains an NVIDIA CUDA build (`torch+cu130`), so it cannot use the Radeon GPU. A separate ROCm environment is provided so the CPU environment is preserved:

```bash
cd /home/wildbot/2026-Meichu-Hackthon/stt
python3 -m venv .venv-rocm
.venv-rocm/bin/python -m pip install --upgrade pip
.venv-rocm/bin/python -m pip install -r backend/requirements.rocm.txt
.venv-rocm/bin/python backend/check_env.py
```

The expected successful classification is `AMD ROCm/HIP`, with `torch.version.hip` set and `torch.cuda.is_available: True`. If it reports no device or fails with a permissions error, the system ROCm runtime or GPU access groups are still missing. AMD's current instructions require ROCm GPU access through the `render` and `video` groups and list the `gfx1152` target; installation of system ROCm packages and group changes require administrator privileges and a reboot.

Start the service with an explicit AMD GPU request after that check passes:

```bash
ASR_DEVICE=rocm .venv-rocm/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
```

In PyTorch, ROCm intentionally uses the device spelling `cuda:0`. `ASR_DEVICE=rocm` validates that the torch build is HIP/ROCm and that a device is available; it fails with a setup error instead of silently falling back to CPU. `ASR_DEVICE=auto` is the resilient default and selects the accelerator when available, while `ASR_DEVICE=cpu` forces the baseline.

Each finalized VAD speech segment is also saved as a local mono 16 kHz WAV under `backend/segments/`. The browser adds a play control beside the finalized transcript, served from the local `/segments/` endpoint. A segment is written after end-of-speech, so continuous microphone transport is still preserved while the saved clip follows the VAD boundary.

## Protocol and measurements

- Browser transport packet: 512 samples, approximately 32 ms.
- VAD: energy gate with pre-roll and one-second end silence.
- Draft: decode the last six seconds at 1.5-second intervals while speech continues.
- Final: decode the entire VAD segment after end-of-speech.
- Final messages include decode latency, segment duration, real-time factor, and wall time.

For lowest live draft latency, the defaults use a four-second sliding window and update every 0.75 seconds. Tune them with `DRAFT_WINDOW_SECONDS=...` and `DRAFT_INTERVAL_SECONDS=...`; shorter values reduce delay but can reduce context and recognition stability. The benchmark sentence is:

> 我們先把 ESP32 的 camera streaming 接起來，然後跑 inference 看一下 latency，確認 WebSocket 有沒有正常工作。

Record model load time from `/healthz`, backend device details from `/diagnostics`, and process CPU/RAM/GPU externally during this sentence. The current CPU path uses 8 threads and BF16 automatically when AVX-512 BF16 is available; override with `STT_CPU_THREADS=...` or `STT_CPU_BF16=0` if benchmarking. Compare `ASR_DEVICE=cpu` with `ASR_DEVICE=rocm` only after a ROCm-enabled torch build has passed the environment check. fp16 is enabled only for a CUDA/HIP torch device.

## Warmed latency benchmark

Run both modes against the same mono 16-bit PCM WAV. Each command warms the
model once, then reports JSON with median/p95 decode latency and real-time
factor:

```bash
cd stt
.venv/bin/python -m backend.benchmark backend/segments/example.wav --device cpu --runs 3
ASR_DEVICE=rocm .venv-rocm/bin/python -m backend.benchmark backend/segments/example.wav --device rocm --runs 3
```

The ROCm result is meaningful only when `check_env.py` reports an available
HIP device. The benchmark measures model decode time, not microphone capture
or network transport, and does not claim a speedup until both runs have been
executed on the target machine.

## Known prototype limits

The energy gate is intentionally dependency-light and should be replaced or augmented with Silero VAD once the transport is validated. Draft decoding is sliding-window local inference, not WhisperLiveKit's AlignAtt implementation. That is the next quality/performance comparison, not a reason to abandon Breeze-ASR-25.

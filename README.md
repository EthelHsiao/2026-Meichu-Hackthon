# Context-Aware boT (CAT)

> Support needs context.

CAT is a physical desk companion that watches how your work is actually going, remembers it,
and responds when you reach out to it. Instead of answering "I'm stuck on my homework" with
generic advice, it can answer with *your* context: what you have been doing, for how long,
and what you already got past.

The system spans three machines: an ESP32-based plush cat, an ASUS PN54 AI PC, and an
AMD Instinct MI300 GPU server.

```
   ┌──────────────┐   sensors / mic      ┌──────────────┐   screenshots      ┌──────────────┐
   │     CAT      │ ───────────────────▶ │  PN54 AIPC   │ ─────────────────▶ │    MI300     │
   │  (ESP32)     │                      │              │   text prompts     │              │
   │ FSR ×2, IMU  │ ◀─────────────────── │ STT, gesture │ ◀───────────────── │ Qwen VLM+LLM │
   │ LCD, buzzer  │  expression + text   │ memory, RAG  │   {expr, text}     │   (Ollama)   │
   └──────────────┘                      └──────────────┘                    └──────────────┘
```

## Repository layout

| Directory | What it is |
| --- | --- |
| [`esp32-bringup/`](esp32-bringup/) | Main board firmware (PlatformIO). FSR402 ×2, MPU6050 IMU, 1.8" TFT LCD, passive buzzer, microphone. Staged `s1`…`s13` environments; `s13_companion` is the full build. |
| [`esp32-cam-bringup/`](esp32-cam-bringup/) | Secondary ESP32-CAM board used by the homework photo flow. |
| [`ai-pc-agent/`](ai-pc-agent/) | The orchestrator on the PN54. Gesture detection, STT bridge, memory store + RAG, prompt assembly, ESP32 WebSocket link. |
| [`stt/`](stt/) | Local Breeze-ASR-25 speech-to-text service (Taiwanese Mandarin with Mandarin–English code switching), CPU or AMD ROCm. |
| [`mi300-deploy/`](mi300-deploy/) | FastAPI service in front of Ollama on the MI300, plus the model benchmark harness. |
| [`docs/`](docs/) | Design notes: [`memory.md`](docs/memory.md), [`data_structures.md`](docs/data_structures.md), [`api.html`](docs/api.html), [`HANDOFF_TODO.md`](docs/HANDOFF_TODO.md). |
| [`problem/`](problem/) | The AMD hackathon problem statement and reference material. |

## Models

| Role | Model | Runs on |
| --- | --- | --- |
| Speech-to-text | Breeze-ASR-25 | PN54 (CPU or ROCm) |
| Text embedding | `BAAI/bge-m3` | PN54 |
| Screen understanding (VLM) | `qwen3.6:35b-a3b-q8_0` (MoE, ~38.7 GB, Q8_0) | MI300 |
| Conversational reply (LLM) | `qwen2.5:7b-instruct` | MI300 |

The 35B VLM is why the MI300 is in the picture at all — at Q8_0 it does not fit on the laptop.
Everything latency- or privacy-sensitive stays local: expressions render on the ESP32,
speech recognition and the long-term memory database never leave the PN54.

Deployed model details and the switch history are in
[`mi300-deploy/bench/DEPLOYED_MODEL.md`](mi300-deploy/bench/DEPLOYED_MODEL.md).

## How it works

### 1. Passive monitoring → memory

`screen_watcher.py` polls desktop state every 10 s (foreground app, window title, process
names, idle time) and captures a screenshot every 30 s. Raw keyboard and mouse input are
never collected.

A screenshot is sent to the MI300 only when `ChangeDetector` sees a meaningful change, and
never more often than once per 60 s. The VLM returns a short description of what the screen
is doing right now; timing, merging, importance and embeddings are all computed locally by
[`ai-pc-agent/memory/store.py`](ai-pc-agent/memory/store.py). The MI300 receives the image as
base64 in the request body and never writes it to disk.

### 2. User wakes CAT

1. The ESP32 streams telemetry every 50 ms. `sensing/gestures.py` turns the raw FSR and IMU
   values into `squeeze` / `pat` / `shake` / `lift` / `putdown` plus a 0–1 intensity, on the PN54.
2. Speech goes to the local Breeze-ASR-25 service over WebSocket.
3. `memory/retrieve.py` runs hybrid retrieval — bge-m3 cosine similarity (0.7) blended with
   SQLite FTS5 BM25 (0.3), scaled by time decay and per-source importance — and takes the
   top 5 memories.
4. `prompt.py` assembles user profile, recent state, retrieved memories, the touch event and
   the utterance into a text prompt for `qwen2.5:7b-instruct`.
5. The model returns `{"expr": <one of 9 expressions>, "text": <short reply>}`. The agent
   streams it to the ESP32 as `SayCommand`, and the LCD shows the face and the caption.

Sending an empty `user_text` signals a proactive utterance, where the model decides whether
to speak at all.

## Running it

### MI300 service

```bash
cd mi300-deploy
docker build -t cat-mi300 .
docker run --rm -p 8000:8000 --device /dev/kfd --device /dev/dri cat-mi300
curl localhost:8000/health
```

`/health` reports the active `text_model` and `vision_model`. `VISION_MODEL` and `TEXT_MODEL`
override the defaults; `/model-lab` is a browser page for stateless prompt and image experiments.

Endpoints: `/v1/screen-observations`, `/v1/chat/completions`, `/v1/homework-analyses`,
`/analyze/screen`, `/models`, `/model-lab`.

### STT service

```bash
cd stt
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
./start_rocm.sh          # or the CPU baseline, see stt/README.md
```

Listens on `ws://127.0.0.1:8765/ws/audio`.

### PN54 agent

```bash
sudo apt install xdotool xprintidle x11-utils procps
cd ai-pc-agent && python3 -m pip install -r requirements.txt

export MI300_API=http://localhost:8000        # via ssh -L port forward
export ESP32_WS_URL=ws://192.168.4.1:81/api/v1/stream

python3 screen_watcher.py                     # passive screen → memory loop
python3 main.py                               # sensors, STT, RAG, replies
```

Every tunable lives in [`ai-pc-agent/config.py`](ai-pc-agent/config.py). A debug dashboard
with gesture injection, memory inspection and retrieval tracing runs from
[`debug_api.py`](ai-pc-agent/debug_api.py) on port 8090.

### Firmware

```bash
cd esp32-bringup
pio run -e s13_companion -t upload
```

The `s1`…`s12` environments bring up one peripheral at a time and are useful when
diagnosing hardware. Pin assignments and the FSR divider rationale are documented in
[`include/board_config.h`](esp32-bringup/include/board_config.h).

> **Networking for demos:** the ESP32-CAM only joins an external hotspot (STA mode), and a
> laptop cannot be on two Wi-Fi networks at once. Put the main board in STA mode as well
> (`TELEMETRY_USE_STA 1`), attach all three devices to the same hotspot, then set
> `ESP32_WS_URL` and `ESP32_CAM_BASE_URL` to the addresses they receive.

## Privacy

- Raw keystrokes and mouse input are never captured.
- Long-term memory, the vector index and speech recognition stay on the PN54.
- The MI300 holds screenshots only in memory for the duration of inference.
- Screenshots **are** written to `./screenshots/` on the PN54 (`SCREENSHOT_DIR`) and there is
  currently no retention policy, so the directory grows without bound. It is gitignored.
  Clearing it is a manual step today — see [`docs/HANDOFF_TODO.md`](docs/HANDOFF_TODO.md).

## Tests

```bash
cd ai-pc-agent && python3 -m pytest
cd mi300-deploy && python3 -m pytest app
```

## Hardware

- ESP32 DevKit V1
- FSR402 force sensors ×2, with 47 kΩ dividers (measured to be far more sensitive than the
  original 10 kΩ at light-to-medium pressure)
- MPU6050 IMU
- 1.8" TFT LCD (ST7735)
- Passive buzzer, microphone
- ESP32-CAM secondary board
- ASUS PN54 AI PC
- AMD Instinct MI300

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'USAGE'
Usage: ./start_rocm.sh

Starts the local Breeze-ASR service on the AMD ROCm device. Override any
setting by putting it before the command, for example:

  ASR_DEVICE=rocm STT_PORT=9000 ./start_rocm.sh
USAGE
  exit 0
fi

PYTHON=""
for candidate in ".venv-rocm-gfx1152/bin/python" ".venv-rocm/bin/python"; do
  if [[ -x "$candidate" ]]; then
    PYTHON="$candidate"
    break
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "No ROCm virtual environment found." >&2
  echo "Create .venv-rocm-gfx1152 or .venv-rocm and install backend/requirements.rocm.txt." >&2
  exit 1
fi

: "${ASR_DEVICE:=rocm}"
: "${SPEECH_START_RMS_THRESHOLD:=0.06}"
: "${SPEECH_CONTINUE_RMS_THRESHOLD:=0.04}"
: "${VAD_START_CHUNKS:=3}"
: "${END_SILENCE_SECONDS:=1.0}"
: "${DRAFT_INTERVAL_SECONDS:=1.5}"
: "${STT_HOST:=127.0.0.1}"
: "${STT_PORT:=8765}"
: "${STT_WS_PING_INTERVAL:=60}"
: "${STT_WS_PING_TIMEOUT:=120}"

export ASR_DEVICE SPEECH_START_RMS_THRESHOLD SPEECH_CONTINUE_RMS_THRESHOLD
export VAD_START_CHUNKS END_SILENCE_SECONDS DRAFT_INTERVAL_SECONDS

exec "$PYTHON" -m uvicorn backend.main:app \
  --host "$STT_HOST" \
  --port "$STT_PORT" \
  --ws-ping-interval "$STT_WS_PING_INTERVAL" \
  --ws-ping-timeout "$STT_WS_PING_TIMEOUT"

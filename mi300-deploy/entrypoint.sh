#!/bin/bash
set -e

# --- sshd（沿用 MLSteam 官方 init.sh 範例的 key 安裝方式）---
mkdir -p /root/.ssh
if [ -f /mlsteam/workspace/.ssh/authorized_keys ]; then
  cp /mlsteam/workspace/.ssh/authorized_keys /root/.ssh/authorized_keys
  chmod 600 /root/.ssh/authorized_keys
  chmod 700 /root/.ssh
fi
/etc/init.d/ssh start || service ssh start || true

# --- Ollama 模型快取一定要指到 /mlsteam/workspace 底下的持久化路徑 ---
# 這台機器「有些地方是 mount 的」：只有 /mlsteam/workspace 會在 LAB 重開後還在，
# 其他路徑（包含預設的 /root/.ollama）LAB 一關就會被清空、模型要重新下載一次。
export OLLAMA_MODELS="${OLLAMA_MODELS:-/mlsteam/workspace/ollama-models}"
mkdir -p "$OLLAMA_MODELS"

# 背景啟動 ollama server
ollama serve &
OLLAMA_PID=$!

# 等 ollama 起來
until curl -sf http://localhost:11434/ >/dev/null 2>&1; do
  sleep 1
done
echo "[entrypoint] ollama serve 已就緒 (pid $OLLAMA_PID)"

# 保底：把預設模型抓下來（已存在就是 no-op，不會重抓）
ollama pull "${MODEL_NAME:-qwen2.5:7b-instruct}" || echo "[entrypoint] 警告：模型 pull 失敗，稍後可手動重試"

echo "[entrypoint] 基礎服務就緒。接下來請用 ssh mi300 連進來執行一次 deploy/bootstrap.sh"

# 保持 container 存活、可看到 ollama log
wait $OLLAMA_PID

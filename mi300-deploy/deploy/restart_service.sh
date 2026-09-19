#!/bin/bash
# 重啟 mi300-api process。手動呼叫，或被 .github/workflows/deploy-mi300.yml 呼叫。
# 用法：restart_service.sh <repo checkout 路徑，底下要有 mi300-deploy/app/main.py>
set -e
APP_DIR="${1:-$GITHUB_WORKSPACE}"
if [ -z "$APP_DIR" ]; then
  echo "用法: $0 <repo checkout 路徑>" >&2
  exit 1
fi

VENV=/mlsteam/workspace/venv
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$APP_DIR/mi300-deploy/app/requirements.txt"

mkdir -p /mlsteam/workspace/logs
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1

cd "$APP_DIR/mi300-deploy/app"
nohup "$VENV/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 \
  > /mlsteam/workspace/logs/mi300-api.log 2>&1 &
disown

sleep 2
if curl -sf http://localhost:8000/health >/dev/null; then
  echo "[restart_service] API 重啟成功"
else
  echo "[restart_service] 健康檢查失敗，log 如下：" >&2
  tail -n 50 /mlsteam/workspace/logs/mi300-api.log >&2
  exit 1
fi

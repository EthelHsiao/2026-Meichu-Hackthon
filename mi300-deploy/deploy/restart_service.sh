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

# 記錄這次部署的 commit 跟時間，讓 /health 跟 dashboard 可以直接看出
# 「有沒有真的換成新版本」，不用去翻 GitHub Actions 分頁或 log。
DEPLOY_SHA=$(git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
DEPLOY_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cd "$APP_DIR/mi300-deploy/app"
# 用 setsid 開一個新 session，不然當這支腳本是被 GitHub Actions runner
# 呼叫時，job 一結束 runner 會把這次 job 產生的整個 process group 收掉，
# 光靠 nohup + disown 擋不住，uvicorn 會在 job "Succeeded" 之後馬上變成
# defunct（實測踩過這個坑：手動跑沒事，CI 觸發就會被殺掉）。
setsid env DEPLOY_SHA="$DEPLOY_SHA" DEPLOY_TIME="$DEPLOY_TIME" \
  "$VENV/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 \
  < /dev/null > /mlsteam/workspace/logs/mi300-api.log 2>&1 &
disown

sleep 2
if curl -sf http://localhost:8000/health >/dev/null; then
  echo "[restart_service] API 重啟成功"
else
  echo "[restart_service] 健康檢查失敗，log 如下：" >&2
  tail -n 50 /mlsteam/workspace/logs/mi300-api.log >&2
  exit 1
fi

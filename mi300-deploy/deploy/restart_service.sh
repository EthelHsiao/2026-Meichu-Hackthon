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
# 注意：這支腳本只能被手動執行或被 watch_and_restart.sh 呼叫，
# 不能被 GitHub Actions job 直接呼叫——job 結束時 runner 會把該次 job
# 產生的整個 process group／cgroup 收掉，nohup／disown／setsid 全部擋
# 不住（2026-09-19 實測踩過），uvicorn 會在 job 回報 Succeeded 後立刻
# 變成 defunct。CI 現在改成呼叫 deploy/trigger_deploy.sh，讓已經常駐、
# 不屬於任何 job 的 watch_and_restart.sh 來呼叫這支腳本。
nohup env DEPLOY_SHA="$DEPLOY_SHA" DEPLOY_TIME="$DEPLOY_TIME" \
  "$VENV/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 \
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

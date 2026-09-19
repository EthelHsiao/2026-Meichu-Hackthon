#!/bin/bash
# 被 .github/workflows/deploy-mi300.yml 呼叫。這支腳本本身跑得很快、
# 跑完就結束（不背景常駐），所以不受 job 結束時 runner 的 process
# cleanup 影響——真正重啟 uvicorn 的動作交給 watch_and_restart.sh
# （已經在 job 開始之前就常駐了）去做，原因見該腳本開頭的說明。
set -e
REPO=/mlsteam/workspace/repo
REF="${GITHUB_REF_NAME:-deploy}"

export GIT_SSH_COMMAND="ssh -F /mlsteam/workspace/.ssh/config"
git -C "$REPO" fetch origin "$REF"
git -C "$REPO" reset --hard "origin/$REF"

SHA=$(git -C "$REPO" rev-parse --short HEAD)
echo "$SHA" > /mlsteam/workspace/.deploy_trigger
echo "[trigger_deploy] 已同步到 $SHA，寫入 trigger，等待 watcher 重啟服務"

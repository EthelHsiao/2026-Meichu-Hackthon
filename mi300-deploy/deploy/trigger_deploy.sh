#!/bin/bash
# 被 .github/workflows/deploy-mi300.yml 呼叫。這支腳本本身跑得很快、
# 跑完就結束（不背景常駐），所以不受 job 結束時 runner 的 process
# cleanup 影響——真正重啟 uvicorn 的動作交給 watch_and_restart.sh
# （已經在 job 開始之前就常駐了）去做，原因見該腳本開頭的說明。
set -e
REPO=/mlsteam/workspace/repo
REF="${GITHUB_REF_NAME:-deploy}"

# /mlsteam/workspace 在這台機器上一律顯示 nobody:nogroup（NFS
# root_squash），較新版 git 會拒絕操作「擁有者不符」的目錄；防禦性地在
# 這裡也設一次，避免 job 環境的 $HOME 跟 bootstrap.sh 設定時不同份。
git config --global --add safe.directory "$REPO" 2>/dev/null || true
export GIT_SSH_COMMAND="ssh -F /mlsteam/workspace/.ssh/config"
git -C "$REPO" fetch origin "$REF"
git -C "$REPO" reset --hard "origin/$REF"

SHA=$(git -C "$REPO" rev-parse --short HEAD)
echo "$SHA" > /mlsteam/workspace/.deploy_trigger
echo "[trigger_deploy] 已同步到 $SHA，寫入 trigger，等待 watcher 重啟服務"

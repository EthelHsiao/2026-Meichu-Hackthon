#!/bin/bash
# 被 .github/workflows/deploy-aipc.yml 呼叫，也可以手動執行來重新部署 AIPC。
#
# 跟 mi300-deploy/deploy/ 那套 trigger_deploy.sh + watch_and_restart.sh 的
# workaround不一樣：那是因為 MI300 的 MLSteam 容器裡沒有 systemd，nohup/disown
# 都擋不住 GitHub Actions runner 在 job 結束時對整個 job cgroup 做的 process
# cleanup。AIPC 是一般 Ubuntu 機器、有 systemd——`systemctl restart` 只是叫
# systemd（PID 1）去管理服務，服務本身跑在 systemd 自己的 cgroup（不是這次
# job 的 cgroup），job 結束的 cleanup 不會波及它，不需要那層 trigger+watcher
# 的間接。2026-09-20 有實際驗證過這個假設成立（見 push 測試紀錄）。
set -e
REPO=/home/wildbot/2026-Meichu-Hackthon
cd "$REPO"
git fetch origin
git reset --hard origin/deploy

cd ai-pc-agent
source .venv/bin/activate
pip install --quiet -r requirements.txt

sudo /home/wildbot/2026-Meichu-Hackthon/ai-pc-agent/deploy/sudo_sync_units.sh

sleep 2
if curl -sf http://localhost:8090/debug/status >/dev/null; then
  echo "[restart_service] dashboard 重啟成功"
else
  echo "[restart_service] 健康檢查失敗，log 如下：" >&2
  sudo journalctl -u ai-pc-agent-dashboard.service -n 50 --no-pager >&2
  exit 1
fi

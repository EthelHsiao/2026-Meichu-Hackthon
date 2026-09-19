#!/bin/bash
# 長駐背景程式，由 bootstrap.sh 啟動一次（不是被 CI job 呼叫）。
#
# 為什麼需要這支腳本：2026-09-19 實測發現，如果讓 GitHub Actions 的
# job 直接（不管用 nohup、disown 還是 setsid）啟動 uvicorn，job 一
# 回報 Succeeded，runner 就會把這次 job 產生的整個 cgroup 殺光，uvicorn
# 會立刻變成 defunct——這是 runner 內建的 process cleanup，跟怎麼背景
# 執行無關，唯一的解法是讓 uvicorn 這個 process 根本不要誕生在任何一次
# job 裡面。
#
# 所以拆成兩段：CI job 只負責把 /mlsteam/workspace/repo 同步到新版本、
# 寫一個 trigger 檔（見 deploy/trigger_deploy.sh）；這支腳本從 job 開始
# 之前就已經在跑、屬於自己的 session，不受任何 job 的 cgroup 管轄，偵測
# 到 trigger 檔內容變了才真的呼叫 restart_service.sh 重啟 uvicorn。
set -u
TRIGGER=/mlsteam/workspace/.deploy_trigger
REPO=/mlsteam/workspace/repo
LAST=""

echo "[watcher] 啟動，監看 $TRIGGER"
while true; do
  if [ -f "$TRIGGER" ]; then
    CUR=$(cat "$TRIGGER" 2>/dev/null || echo "")
    if [ -n "$CUR" ] && [ "$CUR" != "$LAST" ]; then
      echo "[watcher] 偵測到新版本 $CUR，重啟服務"
      if bash "$REPO/mi300-deploy/deploy/restart_service.sh" "$REPO"; then
        LAST="$CUR"
      else
        echo "[watcher] 重啟失敗，$CUR 稍後會重試" >&2
      fi
    fi
  fi
  sleep 3
done

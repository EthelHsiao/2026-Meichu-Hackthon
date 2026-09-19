#!/bin/bash
# 只做「需要 root」的那幾件事：同步 systemd unit 檔、daemon-reload、重啟服務。
# 由 restart_service.sh 透過 sudo 呼叫（sudoers 只允許這一支腳本的固定路徑，
# 見 /etc/sudoers.d/aipc-deploy）。
#
# ⚠️ 安全性提醒：sudoers 對這支腳本開了 NOPASSWD，而這支腳本的內容本身是
# git 版控、跟著 deploy 分支自動部署的——換句話說，任何能推 deploy 分支的人
# 都等於能讓這台機器以 root 執行任意程式碼。這是為了自動部署方便刻意接受的
# 取捨，不是疏忽；如果之後要收緊，改成只允許固定的 systemctl/cp 指令組合
# （犧牲彈性換取限縮 sudoers 的攻擊面）。
set -e
REPO=/home/wildbot/2026-Meichu-Hackthon/ai-pc-agent/deploy

cp "$REPO/ai-pc-mi300-tunnel.service" /etc/systemd/system/
cp "$REPO/ai-pc-agent-dashboard.service" /etc/systemd/system/
cp "$REPO/ai-pc-screen-watcher.service" /etc/systemd/system/
systemctl daemon-reload

systemctl enable --now ai-pc-mi300-tunnel.service
systemctl restart ai-pc-agent-dashboard.service
systemctl enable --now ai-pc-screen-watcher.service
systemctl restart ai-pc-screen-watcher.service

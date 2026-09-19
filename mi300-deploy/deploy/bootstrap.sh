#!/bin/bash
# 在 MI300 LAB 裡「第一次」用 ssh mi300 連進去後手動執行一次。
# 是 idempotent 的：重開 LAB 之後如果發現 runner／服務沒在跑，重跑這支腳本即可。
#
# 用法：
#   REPO_SSH_URL=git@github.com:EthelHsiao/2026-Meichu-Hackthon.git \
#   RUNNER_URL=https://github.com/EthelHsiao/2026-Meichu-Hackthon \
#   RUNNER_TOKEN=<GitHub repo -> Settings -> Actions -> Runners -> New self-hosted runner 現場產生，1小時內有效> \
#   bash bootstrap.sh
set -e

WORK=/mlsteam/workspace
mkdir -p "$WORK/.ssh" "$WORK/repo" "$WORK/actions-runner" "$WORK/logs"

# /mlsteam/workspace 是掛載進來的網路磁碟，裡面所有東西不管誰建的都會
# 顯示成 nobody:nogroup（NFS root_squash），git 新版會把這個所有權不符
# 判定成「dubious ownership」直接拒絕操作。這個設定寫在 $HOME/.gitconfig，
# 不在 /mlsteam/workspace 底下，LAB 重開會消失，所以每次重跑 bootstrap.sh
# 都要重設一次（idempotent，設定同一個值沒有副作用）。
git config --global --add safe.directory "$WORK/repo"

# 1) deploy key —— 第一次跑會產生一把新的，之後重跑偵測到已存在就跳過
if [ ! -f "$WORK/.ssh/id_ed25519" ]; then
  ssh-keygen -t ed25519 -N "" -f "$WORK/.ssh/id_ed25519" -C "mi300-deploy-key"
  echo
  echo "====================================================================="
  echo "把下面這把公鑰加到 GitHub repo -> Settings -> Deploy keys -> Add deploy key"
  echo "（只需要 git pull，勾選唯讀 read-only 就好，不用給 write access）"
  echo "====================================================================="
  cat "$WORK/.ssh/id_ed25519.pub"
  echo "====================================================================="
  echo "貼上去之後，重新執行這支腳本繼續下一步。"
  echo
  exit 0
fi

cat > "$WORK/.ssh/config" << SSHCFG
Host github.com
  HostName github.com
  User git
  IdentityFile $WORK/.ssh/id_ed25519
  StrictHostKeyChecking accept-new
SSHCFG
chmod 600 "$WORK/.ssh/config" "$WORK/.ssh/id_ed25519"
export GIT_SSH_COMMAND="ssh -F $WORK/.ssh/config"

# 2) clone（第一次）或 pull（之後重跑）
#    這份 clone 只是為了在你推第一次 CI 之前就能手動把服務跑起來；
#    之後每次 push 觸發 CI，實際跑的會是 GitHub Actions runner 自己 checkout 的那份。
if [ -z "${REPO_SSH_URL:-}" ]; then
  echo "請設定 REPO_SSH_URL=git@github.com:EthelHsiao/2026-Meichu-Hackthon.git" >&2
  exit 1
fi
if [ ! -d "$WORK/repo/.git" ]; then
  git clone "$REPO_SSH_URL" "$WORK/repo"
else
  git -C "$WORK/repo" pull
fi

# 3) GitHub Actions self-hosted runner —— 一次性安裝，重跑會偵測已安裝就跳過下載
cd "$WORK/actions-runner"
if [ ! -f "./config.sh" ]; then
  ARCH=$(uname -m)
  case "$ARCH" in
    x86_64) RARCH=x64 ;;
    aarch64) RARCH=arm64 ;;
    *) echo "不支援的架構 $ARCH" >&2; exit 1 ;;
  esac
  RUNNER_VER=2.319.1
  curl -o actions-runner.tar.gz -L \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VER}/actions-runner-linux-${RARCH}-${RUNNER_VER}.tar.gz"
  tar xzf actions-runner.tar.gz
  rm actions-runner.tar.gz
fi

if [ ! -f ".runner" ]; then
  if [ -z "${RUNNER_URL:-}" ] || [ -z "${RUNNER_TOKEN:-}" ]; then
    echo "請提供 RUNNER_URL 與 RUNNER_TOKEN" >&2
    echo "(GitHub repo -> Settings -> Actions -> Runners -> New self-hosted runner 現場產生，1小時內有效)" >&2
    exit 1
  fi
  # MLSteam 這個 pod 裡沒有非 root 使用者，容器內一律用 root 跑，
  # 所以要靠 RUNNER_ALLOW_RUNASROOT 跳過 runner 預設的「不能用 root 裝」檢查。
  RUNNER_ALLOW_RUNASROOT=1 ./config.sh --url "$RUNNER_URL" --token "$RUNNER_TOKEN" \
    --name "mi300-$(hostname)" --labels mi300 --work "_work" --unattended --replace
fi

# 4) 背景啟動 runner（容器裡通常沒有 systemd，用 nohup；LAB 重開後要重跑這支腳本才會重新背景啟動）
if ! pgrep -f "bin/Runner.Listener" >/dev/null 2>&1; then
  nohup env RUNNER_ALLOW_RUNASROOT=1 ./run.sh > "$WORK/logs/actions-runner.log" 2>&1 &
  disown
  echo "[bootstrap] GitHub Actions runner 已在背景啟動（label: mi300）"
else
  echo "[bootstrap] runner 已經在跑，略過"
fi

# 5) 先手動起一次 API service，之後每次 push 到指定分支會由 CI 接手重啟
bash "$WORK/repo/mi300-deploy/deploy/restart_service.sh" "$WORK/repo"

# 6) 背景啟動 deploy watcher——一定要在這裡（bootstrap.sh 手動執行的當下）
#    啟動，不能讓 CI job 自己去啟動它，理由見 watch_and_restart.sh 開頭
#    的說明（job 結束時 runner 會殺光這次 job 產生的整個 process
#    group／cgroup，包含任何自稱有 nohup／disown／setsid 的常駐 process）。
if ! pgrep -f "watch_and_restart.sh" >/dev/null 2>&1; then
  nohup bash "$WORK/repo/mi300-deploy/deploy/watch_and_restart.sh" \
    > "$WORK/logs/deploy-watcher.log" 2>&1 &
  disown
  echo "[bootstrap] deploy watcher 已在背景啟動"
else
  echo "[bootstrap] deploy watcher 已經在跑，略過"
fi

echo
echo "[bootstrap] 完成。健康檢查：curl http://localhost:8000/health"

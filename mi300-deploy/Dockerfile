# 給 MLSteam「準備 Docker Image -> a. Build From Dockerfile」用的自訂範本。
# 只裝環境，不把 app code COPY 進 image —— app code 一律從 git checkout 讀取，
# 這樣改 app/main.py 不需要重建 image、只需要 CI 重啟 process（見 deploy/restart_service.sh）。
# 之後若要換 base ROCm 版本 / 裝新的系統套件，才需要重建這個 image。

FROM ollama/ollama:rocm

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv \
    openssh-server \
    git curl \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /var/run/sshd

# ollama/ollama:rocm 原本的 ENTRYPOINT 會自動執行 `ollama serve`，
# 我們接手改成先跑 entrypoint.sh 再啟動 ollama + sshd，app process 交給
# deploy/bootstrap.sh 之後另外用 nohup 啟動（不放進 image 的 CMD，
# 因為第一次一定要先跑 bootstrap 裝 GitHub Actions runner）。
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 11434 8000 22
ENTRYPOINT ["/entrypoint.sh"]

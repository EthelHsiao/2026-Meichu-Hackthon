# MI300 部署設定 — 陪碼

這個資料夾是幫你把 `2026-Meichu-Hackthon` 這個 private repo 部署到 MI300（MLSteam / Manta 平台）
上要用到的所有東西：Docker image、要跑的服務、GitHub Actions 自動部署設定、
以及每一步在 `ssh mi300` 裡要打的指令。

先講結論，細節在下面：

1. **MI300 上只需要跑一個服務**：Ollama（模型推論）+ 一個薄薄的 FastAPI wrapper（`app/main.py`）。
   AI PC 才是真正的協調中樞，ESP32 是邊緣端 —— 這兩層不部署在 MI300 上。
2. 這台機器**只有 `/mlsteam/workspace` 是 mount（重開 LAB 還在）**，其他路徑都是這個 pod 專屬、
   關掉就消失。所有東西（repo clone、GitHub Actions runner、python venv、ollama 模型快取、
   deploy key）都刻意放在 `/mlsteam/workspace` 底下。
3. 自動部署用的是 **GitHub Actions self-hosted runner**，跑在 MI300 這個 pod 裡自己去 GitHub
   長輪詢拉 job，而不是讓 GitHub 反過來打進來 —— 因為 MI300 在校網 NAT 後面，
   校方不太可能幫你開對外可連的 inbound port，self-hosted runner 完全不需要 inbound，
   只要 pod 能對外連到 github.com 就行。

---

## 0. 為什麼只需要這一個服務（對照你的 spec）

`claude/HACKATHON_PROPOSAL_SPEC.md` 第 4 節已經把三層架構的分工寫死了：

| 層級 | 部署在哪 | 這次要不要動 |
|---|---|---|
| ESP32（Edge） | 燒錄到板子上 | 不在這次範圍 |
| AI PC（本機協調） | 比賽用的筆電本機 process | 不在這次範圍 |
| **MI300** | **這裡** | ✅ |

MI300 明確只在兩種情況被呼叫（spec 原文）：

1. 自然語言轉鬧鐘（U04：「我好累想睡半小時」→ 分鐘數）
2. 「陪你等 agent」情境的 affect labeling 一句反映

兩個都是「給結構化摘要、要一個小小的文字/JSON 回應」的簡單 LLM 呼叫，不需要對話記憶、
不需要看畫面或程式碼內容（spec 第 9 節也明講這是刻意的隱私設計）。所以 MI300 上：

- **需要**：一個模型推論服務（Ollama）+ 一個把這兩個呼叫包成穩定 API 的 wrapper（`app/main.py`
  的 `/parse-timer`、`/affect-label`）。
- **不需要**：資料庫、對話記憶服務、任何常駐 state（那些如果要做，屬於 AI PC 那層）、
  webcam/影像處理（第一版明確排除）。

如果之後你們真的要加影像/VLM 判斷之類的功能，才需要在這份清單上加新服務——目前 spec 定義的
範圍不需要。

---

## 1. 這台機器的 mount 是怎麼回事

MLSteam 是 Kubernetes 架構，"LAB"（你 SSH 連進去的那個 container）本質上是一個 pod：

- **`/mlsteam/workspace`**：帳號隔離的持久化工作區，新建專案自動產生，LAB 關掉重開還在。
- **其他所有路徑**（`/root`、`/home`、image 裡裝的東西）：LAB 一關就恢復成 image 原本的樣子，
  裝的套件、clone 的 repo、產生的 key 全部消失。

所以這份設定的每一步都刻意把「有狀態」的東西放進 `/mlsteam/workspace`：

```
/mlsteam/workspace/
├── .ssh/id_ed25519(.pub)   # deploy key，只讀權限拉 private repo
├── repo/                    # git clone（手動起服務用，見下面）
├── actions-runner/          # GitHub Actions self-hosted runner 安裝目錄 + _work/
├── ollama-models/           # ollama 模型快取（不放這裡的話，重開 LAB 要重抓模型）
├── venv/                    # python virtualenv
└── logs/                    # nohup 的 stdout/stderr
```

**LAB 重開後只要做一件事**：`ssh mi300` 進去，重跑一次 `bootstrap.sh`（見第 4 節），
它是 idempotent 的，deploy key／repo clone／runner 安裝都已存在就會跳過，
只會重新把 runner 和 API service 背景啟動起來。

---

## 2. 建立 MI300 LAB（在 MLSteam 網頁上）

兩個做法，時間緊建議先用第一個：

**做法 A（推薦，比賽時間內先用這個）**：直接照教學 4.3.2 節「從網路 Docker Hub 建立映像檔」
拉 `ollama/ollama:rocm` 當範本，跳過 build 步驟，最快能 SSH 進去。
`ollama/ollama:rocm` 這個 base image 沒有內建 `git`/`python3`/`openssh-server`，
所以 SSH 進去後第一件事要先手動裝：
`apt-get update && apt-get install -y git python3 python3-venv openssh-server curl`，
裝完再跑 `bootstrap.sh`（下面第 4 節已經把這個順序寫進指令了）。

**做法 B（比較穩，但要多等一次 build）**：把這個資料夾的 `Dockerfile` 上傳到 MLSteam 的
「資料夾」功能（4.2 節），用「Build From Dockerfile」（4.3.1 節）建出自己的 image，
裡面已經把 `git`/`python3`/`openssh-server` 都裝好、`entrypoint.sh` 會自動處理
sshd 啟動與 `OLLAMA_MODELS` 指到 `/mlsteam/workspace/ollama-models`。之後從這個
image 建 LAB，開機就緒後只需要跑 `bootstrap.sh`。

建 LAB 時記得：

- 硬體規格選夠跑 7B–8B 模型的 GPU 額度（預設配額 96GB VRAM 綽綽有餘）。
- 確認 `/mlsteam/workspace` 有掛載（這應該是預設行為）。
- 如果 UI 有讓你設定環境變數的欄位，設 `OLLAMA_MODELS=/mlsteam/workspace/ollama-models`，
  模型快取才會活過 LAB 重開；沒有這個欄位就照做法 B 用 `entrypoint.sh` 處理。
- 依教學 4.6.3–4.6.5 節，或直接用你現有的 `ssh mi300` 設定，把 SSH port forward 打開，
  確保 `ssh mi300` 能連進去。

---

## 3. GitHub 這邊要先做的兩件事

### 3.1 Deploy key（讓 MI300 能 pull 這個 private repo）

不用共用你自己的 GitHub 帳號憑證——`bootstrap.sh` 第一次執行會在 MI300 上產生一把新的
ed25519 key 並印出公鑰，你只要：

1. 打開 `https://github.com/EthelHsiao/2026-Meichu-Hackthon/settings/keys`
2. Add deploy key，貼上 `bootstrap.sh` 印出來的公鑰
3. **不要**勾 "Allow write access"（只需要 pull，唯讀就夠，降低風險）

### 3.2 Self-hosted runner 註冊 token

1. 打開 `https://github.com/EthelHsiao/2026-Meichu-Hackthon/settings/actions/runners/new`
2. 選 Linux / x64，頁面會給你一段 `--token XXXX` 的字串（1 小時內有效，過期重開頁面拿新的）
3. 記下這個 token 和頁面上顯示的 URL（就是 repo 網址本身）

### 3.3 把 workflow 檔放進 repo

把 `mi300-deploy/.github-workflow/deploy-mi300.yml` 搬到 repo 根目錄的
`.github/workflows/deploy-mi300.yml`（GitHub 只認這個固定路徑）。

預設觸發分支是 `deploy`——**建議刻意分出一個獨立的 `deploy` 分支**，而不是每次 push
`main` 就重啟服務：這樣你在 `main`/功能分支上正常開發、頻繁 commit，
只有真的要更新展示機時才 merge 進 `deploy`，比較不會在排練到一半時被自動重啟打斷。
如果你比較想要「push main 就自動部署」，把 `deploy-mi300.yml` 裡的
`branches: [deploy]` 改成 `branches: [main]` 或 `[main, deploy]` 都可以。

把整個 `mi300-deploy/` 資料夾（含 `app/`、`Dockerfile`、`entrypoint.sh`、`deploy/`）
`git add` 進 repo 一起 commit、push 上去。

---

## 4. 在 MI300 上執行（`ssh mi300`）

```bash
ssh mi300

# 如果是用做法 A（沒 build 自訂 image），先確保工具都在：
apt-get update && apt-get install -y --no-install-recommends \
  git python3 python3-venv openssh-server curl
/etc/init.d/ssh start || service ssh start

# 把 bootstrap.sh 抓下來(可以先 scp 上去，或直接用 GitHub raw —— 但這時候還沒有 deploy key，
# 建議第一次用 scp：從你自己電腦 `scp mi300-deploy/deploy/bootstrap.sh mi300:/mlsteam/workspace/`)

cd /mlsteam/workspace
REPO_SSH_URL=git@github.com:EthelHsiao/2026-Meichu-Hackthon.git \
  bash bootstrap.sh
# 第一次跑會印出公鑰然後就退出 —— 照第 3.1 節貼到 GitHub Deploy keys，然後重跑：

REPO_SSH_URL=git@github.com:EthelHsiao/2026-Meichu-Hackthon.git \
RUNNER_URL=https://github.com/EthelHsiao/2026-Meichu-Hackthon \
RUNNER_TOKEN=<第 3.2 節拿到的 token> \
  bash bootstrap.sh
```

跑完會看到 `[bootstrap] 完成`，測試一下：

```bash
curl http://localhost:8000/health
# {"ok":true,"model":"qwen2.5:7b-instruct","ollama_url":"http://localhost:11434"}

curl -X POST http://localhost:8000/parse-timer \
  -H 'content-type: application/json' \
  -d '{"utterance":"我好累，想睡半小時"}'
# {"minutes":30}
```

之後你在本機 `git push` 到 `deploy` 分支，GitHub 會自動排到這台 runner 上執行
`deploy-mi300.yml`，重新 `git pull` + 重啟 API process ——不需要再手動連進去。

---

## 5. AI PC 怎麼打到這個 API

比賽現場 AI PC 和 MI300 大概率不在同一區網，最省事的方式是直接沿用你已經有的
`ssh mi300` 設定開 local port forward，在 AI PC 上跑：

```bash
ssh -N -L 8000:localhost:8000 mi300
```

然後 AI PC 端的程式打 `http://localhost:8000/parse-timer`、`http://localhost:8000/affect-label`
就好，不用另外去研究 MLSteam 平台的 Port Forward / WebApp 功能（教學 4.7 節那套是給要對外
公開網頁用的，你們這個場景是 AI PC 主動連出去，SSH tunnel 更快更穩，比賽現場也不用擔心
額外開 port 的審核流程）。

---

## 6. 已知待確認事項

- Spec 裡提到「AI PC」在賽題定義裡是否特指 AMD Ryzen AI（NPU）機種，如果是的話，
  「Edge deployment」那段論述需要團隊手上的筆電支援——這件事跟 MI300 部署本身無關，
  但簡報前要確認。
- 這裡預設模型是 `qwen2.5:7b-instruct`（中文短句生成效果通常不錯、7B 延遲低適合現場 demo）。
  想換模型只要改 `docker-compose`/環境變數裡的 `MODEL_NAME`，或直接
  `ollama pull <新模型>` 後改 `bootstrap.sh`/`restart_service.sh` 呼叫時的環境變數。
- Fallback：MI300 API 若比賽現場斷線，spec 第 8 節本來就建議準備寫死的 fallback 反映句，
  這份 wrapper 沒有內建這個備援，需要的話在 AI PC 那端做（`/affect-label` 呼叫失敗時
  用本地隨機挑句子取代），這樣才不會整個 demo 卡住。

# MI300 部署 Runbook — 陪碼

這份文件是給任何人（包含另一個 Claude session）接手執行剩下步驟用的，
寫的時候假設執行者對這個專案沒有背景，只看這份文件跟這個資料夾就要能做完。

---

## 0. 現況（2026-09-19 更新，第一輪部署已完成）

- MI300 LAB 已經在跑：MLSteam 平台上一個叫 `test` 的 project，狀態 `Running`，
  是 **basic 模板**（沒有內建 docker／ollama，但 `rocm-smi` 確認 GPU 可用）。
- 連線方式：使用者有 `ssh mi300` 的本機設定；另外 MLSteam 網頁的 project 頁面
  裡也有一個內建網頁終端（點進 project 就看得到），**兩個是同一台機器**。
- ⚠️ **關於網頁終端 vs. 直接 `ssh mi300`**：MLSteam 網頁裡那個內建終端是用
  canvas 渲染的，瀏覽器自動化工具（合成按鍵事件）進不去，這點還是真的。
  但**如果執行者（含 Claude session）在本機終端環境有 shell 工具可用**，
  直接對 `ssh mi300` 下指令是完全正常的一般 SSH session，跟那個網頁終端無關、
  不受這個限制——2026-09-19 這輪就是這樣直接跑完全部步驟的，不需要請人類
  逐句貼指令。只有在**沒有 shell/Bash 工具、只能操作瀏覽器**的環境下，才需要
  退回「印指令給使用者、請她貼進網頁終端、貼結果回來」這個接力模式。
  MLSteam 網頁 UI 的按鈕點擊（不是終端機本身）從來不受此限制，例如第 6 節
  要開 Port Forward／建 WebApp，那些是正常 DOM 元素。
- ⚠️ **兩個踩過的坑，`bootstrap.sh`／README 已經修正**：
  1. `ollama` 安裝腳本需要 `zstd` 解壓縮，basic 模板沒有內建，要先
     `apt-get install -y zstd`（連同 `git`、`python3-venv` 一起裝，見第 3 節）。
  2. 這個容器沒有非 root 使用者、一律用 root 跑，GitHub Actions runner 的
     `config.sh`／`run.sh` 預設拒絕 root（`Must not run with sudo`），要帶
     `RUNNER_ALLOW_RUNASROOT=1`（`bootstrap.sh` 已內建這個環境變數）。
- 待辦進度（勾了的是已確認完成）：
  - [x] `curl -fsSL https://ollama.com/install.sh | sh` 裝 Ollama
  - [x] `ollama serve` 背景啟動、`OLLAMA_MODELS` 指到 `/mlsteam/workspace/ollama-models`
  - [x] `ollama pull qwen2.5:7b-instruct`（文字：計時器解析、affect-label、摘要）
  - [x] `ollama pull llava:7b`（視覺：螢幕截圖描述）
  - [x] 產生 deploy key、貼到 GitHub repo 的 Deploy keys
  - [x] `git clone` private repo 到 `/mlsteam/workspace/repo`
  - [x] 裝 GitHub Actions self-hosted runner、註冊、背景啟動
  - [x] 手動跑一次 `restart_service.sh`，確認 `curl localhost:8000/health` 正常
  - [x] 把 `mi300-deploy/` 整個資料夾、`.github-workflow/deploy-mi300.yml`
        搬到 repo 根目錄的 `.github/workflows/deploy-mi300.yml`，commit + push
  - [ ] （加分）在 MLSteam 網頁上把 8000 port 開成 WebApp，拿到公開展示網址

- 這份 repo（`2026-Meichu-Hackthon`）目前是 **private**，帳號 `EthelHsiao`。

---

## 1. 這整套在解決什麼問題（架構總覽）

專案是一個 context-aware 桌面陪伴機器人，完整定案在 project 裡的
`claude/HACKATHON_PROPOSAL_SPEC.md`（第 4 節架構、第 12 節這次 MI300 部署帶出的
範圍異動）。三層分工：

| 層級 | 在哪裡跑 | 負責什麼 |
|---|---|---|
| ESP32 | 燒錄到板子上 | 邊緣端感測（FSR／IMU）、LCD、本地 state machine |
| AI PC | 比賽用筆電 | 本機協調：監看 coding agent process、計時器、**螢幕截圖背景程式** |
| **MI300（這份文件的範圍）** | 這裡 | 語言／視覺理解：計時器解析、affect-label 反映、螢幕描述、記憶摘要、展示 dashboard |

MI300 上實際要跑的東西只有**一個 process**：一支 FastAPI app（`app/main.py`），
背後呼叫本機的 Ollama 做推論。不需要額外的資料庫服務、不需要 nginx、
不需要 docker-compose——所有「記憶」用一個 SQLite 檔案就解決。

---

## 2. 這台機器的 mount 是怎麼回事（一定要先懂，不然重開 LAB 會全部消失）

MLSteam 是 Kubernetes 架構，你 SSH／網頁終端連進去的東西本質上是一個 pod：

- **`/mlsteam/workspace`**：帳號隔離的持久化工作區，LAB 關掉重開還在。
- **其他所有路徑**（`/root`、image 裡裝的套件）：LAB 一關就恢復成 image 原本
  的樣子，裝的東西、clone 的 repo、產生的 key 全部消失。

所以以下每一步都刻意把「有狀態」的東西放進 `/mlsteam/workspace`：

```
/mlsteam/workspace/
├── ollama-models/       # ollama 模型快取
├── memory.db            # SQLite，事件流 + 摘要（第 7 節）
├── .ssh/id_ed25519(.pub)  # deploy key，唯讀權限拉 private repo
├── repo/                # git clone
├── actions-runner/      # GitHub Actions self-hosted runner
├── venv/                # python virtualenv
└── logs/                # nohup 的 stdout/stderr
```

**LAB 重開後只要做一件事**：連進終端機，重跑一次 `deploy/bootstrap.sh`。
它是 idempotent 的——deploy key／repo clone／runner 安裝都已存在就會跳過，
只會重新把 runner 和 API service 背景啟動起來（因為容器裡沒有 systemd，
process 不會自動在重開後復活）。

---

## 3. 在 MI300 終端機裡執行 — Ollama

```bash
apt-get update && apt-get install -y --no-install-recommends zstd git python3-venv
mkdir -p /mlsteam/workspace/logs /mlsteam/workspace/ollama-models
curl -fsSL https://ollama.com/install.sh | sh
nohup env OLLAMA_MODELS=/mlsteam/workspace/ollama-models ollama serve \
  > /mlsteam/workspace/logs/ollama.log 2>&1 &
disown
sleep 3
curl -s http://localhost:11434/
echo
ollama pull qwen2.5:7b-instruct
ollama pull llava:7b
```

確認：兩個 `ollama pull` 都印出 `success`；`curl http://localhost:11434/`
回 `Ollama is running`。

---

## 4. GitHub 這邊要先做的兩件事

### 4.1 Deploy key（讓 MI300 能 pull 這個 private repo，不用共用你自己的帳號憑證）

`deploy/bootstrap.sh` 第一次執行會在 MI300 上產生一把新的 ed25519 key 並印出公鑰：

1. 打開 `https://github.com/EthelHsiao/2026-Meichu-Hackthon/settings/keys`
2. Add deploy key，貼上印出來的公鑰
3. **不要**勾 "Allow write access"（只需要 pull，唯讀就夠）

### 4.2 Self-hosted runner 註冊 token

1. 打開 `https://github.com/EthelHsiao/2026-Meichu-Hackthon/settings/actions/runners/new`
2. 選 Linux / x64，頁面會給一段 `--token XXXX`（**1 小時內有效**，過期重開頁面拿新的）
3. 記下這個 token，跟頁面上顯示的 URL（就是 repo 網址本身）

### 4.3 把 workflow 檔放進 repo

把這個資料夾的 `.github-workflow/deploy-mi300.yml` 搬到 repo 根目錄的
`.github/workflows/deploy-mi300.yml`（GitHub 只認這個固定路徑），
連同整個 `mi300-deploy/`、`ai-pc-agent/` 資料夾一起 commit、push。

---

## 5. 在 MI300 終端機裡執行 — deploy key、clone、runner、啟動服務

先確保基本工具都在（basic 模板沒有內建）：

```bash
apt-get update && apt-get install -y --no-install-recommends git python3 python3-venv curl
```

第一次跑 `bootstrap.sh`（會停在印出公鑰的地方）：

```bash
cd /mlsteam/workspace
REPO_SSH_URL=git@github.com:EthelHsiao/2026-Meichu-Hackthon.git \
  bash repo/mi300-deploy/deploy/bootstrap.sh
```

> 這裡假設 repo 已經 clone 過一次才有 `repo/mi300-deploy/deploy/bootstrap.sh` 這個路徑；
> 如果是全新環境、repo 還沒 clone，先手動 `git clone` 一次到 `/mlsteam/workspace/repo`
> 取得這支腳本，或直接把 `bootstrap.sh` 內容用 `cat > bootstrap.sh << 'EOF' ... EOF`
> 貼進終端機建立起來，再執行。

照第 4.1 節把印出來的公鑰貼到 GitHub，然後帶著 runner token 重跑一次：

```bash
REPO_SSH_URL=git@github.com:EthelHsiao/2026-Meichu-Hackthon.git \
RUNNER_URL=https://github.com/EthelHsiao/2026-Meichu-Hackthon \
RUNNER_TOKEN=<第 4.2 節拿到的 token> \
  bash /mlsteam/workspace/repo/mi300-deploy/deploy/bootstrap.sh
```

跑完會看到 `[bootstrap] 完成`。驗證：

```bash
curl http://localhost:8000/health
# {"ok":true,"text_model":"qwen2.5:7b-instruct","vision_model":"llava:7b","ollama_url":"http://localhost:11434"}

curl -X POST http://localhost:8000/parse-timer \
  -H 'content-type: application/json' -d '{"utterance":"我好累，想睡半小時"}'
# {"minutes":30}
```

---

## 6. GitHub 自動 push-and-deploy 是怎麼運作的

**原理**：不是 GitHub 打進 MI300（校網 NAT 後面，GitHub 根本連不到你），
而是反過來——MI300 上跑一個 **self-hosted runner** process，它主動連出去
long-poll GitHub「有沒有工作要我做」。你一 push，GitHub 幫你把
`.github/workflows/deploy-mi300.yml` 這個 job 排給這台 runner，runner 抓下來
執行。全程都是 MI300 主動對外連線，完全不需要開 inbound port。

**觸發分支**：`deploy-mi300.yml` 裡預設是 `branches: [deploy]`——建議你在 `main`／
功能分支正常開發，真的要更新展示機才 merge 進獨立的 `deploy` 分支，這樣不會
在排練排到一半時被自動重啟打斷。想改成 push `main` 就自動部署，把那行改成
`branches: [main]` 或 `[main, deploy]`。

**實際執行的事（2026-09-19 改過架構，見下面的坑）**：workflow 只有一步——
跑 `deploy/trigger_deploy.sh`，把 `/mlsteam/workspace/repo` 同步到這次 push
的版本、寫一個 trigger 檔。**不會重建 Ollama**，Ollama 是獨立長跑的 process，
跟這次部署無關；只有 `app/main.py` 這支 API 會被換成最新版本。

⚠️ **踩過的坑：不能讓 CI job 直接啟動 uvicorn**——第一次實測（2026-09-19）
發現 job 回報 `Succeeded` 之後，剛啟動的 uvicorn 立刻變成 defunct，`nohup`、
`disown`、甚至 `setsid` 都擋不住。原因是 self-hosted runner 用 cgroup 追蹤
一個 job 產生的整個 process tree，job 一結束就把 cgroup 裡的東西全部殺掉，
跟你怎麼背景執行無關——只要 process 是在 job 裡「誕生」的，就跑不掉。

**解法**：把「拿新 code」跟「重啟 process」拆成兩支獨立的腳本：
- `deploy/trigger_deploy.sh`——CI job 呼叫的就是這支，跑很快、跑完就結束
  （把 `/mlsteam/workspace/repo` fetch + reset --hard 到新版本、寫入
  `/mlsteam/workspace/.deploy_trigger`），job 結束時它早就退出了，cgroup
  cleanup 殺不到已經不存在的 process。
- `deploy/watch_and_restart.sh`——由 `bootstrap.sh`（人工執行，不是 CI）
  啟動的長駐 loop，每 3 秒檢查 trigger 檔內容有沒有變，變了才呼叫
  `deploy/restart_service.sh` 真的去重啟 uvicorn。因為這支 watcher 从一
  開始就不屬於任何 job 的 process tree，它自己（跟它啟動的 uvicorn 子
  process）完全不受 CI job 的 cgroup cleanup 影響。

**另一個順便踩到的坑**：`/mlsteam/workspace` 這個網路磁碟不管誰建立檔案，
`ls -la` 都顯示 `nobody:nogroup`（NFS root_squash），git 新版看到「跑
git 指令的使用者」跟「目錄擁有者」對不上會直接拒絕（`dubious ownership`）。
`bootstrap.sh` 開頭跟 `trigger_deploy.sh` 都已經加上
`git config --global --add safe.directory ...` 處理這個。

**LAB 重開後**：除了原本第 2 節說的「重跑 `bootstrap.sh`」，現在它還會
順便重新背景啟動 `watch_and_restart.sh`（原本就是 idempotent 設計，偵測
已經在跑就跳過）。

**驗證自動部署**：GitHub repo 頁面的 Actions 分頁可以看到每次 push 觸發的
job 有沒有成功；MI300 上 `/mlsteam/workspace/logs/mi300-api.log` 可以看實際
process 的輸出。

---

## 7. 螢幕摘要 + 記憶結構 + 展示 dashboard（2026-09-19 排入主線的範圍，見 spec 第 12 節）

- `app/main.py` 新增：`POST /events/screen`（截圖 → llava 產生英文描述 → 文字模型
  轉繁中一句話 → 存事件，圖片本體不落地）、`POST /events/note`（直接記一句話）、
  `GET /status`（dashboard 讀取，背景 60 秒重新摘要一次）、`GET /`（展示用
  dashboard 網頁，**沒有真的帳號密碼登入**，純狀態頁給評審看）。
- 記憶結構：`/mlsteam/workspace/memory.db`（SQLite），`events` 表存原始事件流，
  `state` 表存背景 loop 壓縮出的目前摘要。
- AI PC 端：`ai-pc-agent/screen_watcher.py`，每 5 秒截圖、縮小壓縮成 JPEG、
  base64 POST 給 `/events/screen`；透過 `ssh -N -L 8000:localhost:8000 mi300` 連線。
- **已知代價**：這讓 MI300 從無狀態變成有狀態服務，跟 spec 原本設計不完全一致，
  簡報要老實講這是黑客松時程內的權衡，細節見 spec 第 12 節。

**要給評審一個不用透過 SSH tunnel 就能開的公開網址**：在 MLSteam 網頁 project
頁面上把這個 container 的 8000 port 建成一個 WebApp／開 Port Forward
（跟教學裡 Streamlit 範例是同一套功能）。這步是點網頁 UI，不是打終端機指令，
不受第 0 節提到的終端機限制，可以請 Claude 在瀏覽器面板裡操作。

---

## 8. AI PC 怎麼打到這個 API（沒有公開網址時的預設做法）

```bash
ssh -N -L 8000:localhost:8000 mi300
```

AI PC 端程式打 `http://localhost:8000/...` 就好。

---

## 9. 2026-09-19 部署驗證紀錄（怎麼確認第 0-5 節都真的做完）

這次是由一個有本機 shell 存取權的 Claude session 直接 `ssh mi300` 跑完
第 3、4、5 節，不是請人手動貼指令。跑完後用下面這幾條指令驗證，任何人
（包含之後接手的另一個 Claude session）都可以重新對 `ssh mi300` 跑一次
確認現況：

```bash
# 1) API 活著、模型設定正確
ssh mi300 "curl -s http://localhost:8000/health"
# 預期：{"ok":true,"text_model":"qwen2.5:7b-instruct","vision_model":"llava:7b","ollama_url":"http://localhost:11434"}

# 2) 文字模型真的能推論（不是回傳假資料）
ssh mi300 "curl -s -X POST http://localhost:8000/parse-timer -H 'content-type: application/json' -d '{\"utterance\":\"我好累，想睡半小時\"}'"
# 預期：{"minutes":30}

# 3) 三個背景 process 都還活著（LAB 沒有重開過就應該一直在）
ssh mi300 "pgrep -af 'ollama serve'; pgrep -af Runner.Listener; curl -s http://localhost:11434/"
# 預期：兩個 pgrep 各印出一行 PID + 指令，curl 印出 "Ollama is running"

# 4) runner 真的有註冊、有在 listen（不是 process 活著但沒連上 GitHub）
ssh mi300 "tail -5 /mlsteam/workspace/logs/actions-runner.log"
# 預期看到 "Listening for Jobs"

# 5) 模型檔案真的落在持久化路徑，LAB 重開不會消失
ssh mi300 "du -sh /mlsteam/workspace/ollama-models"
```

這輪實際跑出來的結果（2026-09-19）：`/health` 和 `/parse-timer` 都符合預期；
`ollama serve`（pid 105373）、`Runner.Listener`（pid 105767）都在跑；
runner log 顯示 `Listening for Jobs`。

**怎麼驗證「push 真的觸發了自動部署」，不需要開瀏覽器看 Actions 分頁**：
`restart_service.sh` 每次重啟都會把當下的 git commit（短 SHA）跟 UTC 時間
寫進環境變數，`/health`、`/status`、dashboard 頁尾都看得到：

```bash
ssh mi300 "curl -s http://localhost:8000/health"
# {"ok":true,...,"deploy_sha":"71d7428","deploy_time":"2026-09-19T05:45:58Z"}
```

Push 前後各查一次這個欄位，`deploy_sha` 換成你剛剛 push 的 commit 短碼，
就代表自動部署真的换成新版本了——不用猜、不用翻 log。

**這輪已經實際 push 過 `deploy` 分支驗證，而且第一次就失敗過**：第一次
push 後 GitHub Actions job 顯示 `Succeeded`，但 `deploy_sha` 沒有更新、
`ssh mi300 "pgrep -af uvicorn"` 看到的 process 變成 `<defunct>`——服務其實
掛了，只是 job 本身沒有失敗（因為 job 在它自己回報成功之前，`restart_service.sh`
內建的健康檢查是有過的，是 job 結束「之後」runner 的 cleanup 才把 process
殺掉）。這就是上面第 6 節那個 cgroup 坑，改成 trigger 檔 + 常駐 watcher
架構之後重新 push 測試（commit `bcd8d5e`），`deploy_sha` 正確换成
`bcd8d5e`、process 存活，之後又觀察了幾秒確認沒有再被殺掉。

---

## 10. 已知待確認事項

- Spec 裡「AI PC」在賽題定義裡是否特指 AMD Ryzen AI（NPU）機種，如果是的話
  team 手上的筆電要先確認符合——這件事跟 MI300 部署本身無關，但簡報前要確認。
- Fallback：MI300 API 若比賽現場斷線，spec 第 8 節建議準備寫死的 fallback
  反映句；這份 wrapper 沒有內建，需要的話在 AI PC 端做（呼叫失敗時本地隨機
  挑句子取代），避免整個 demo 卡住。

---

## 11. 現在的模型是不是能力不夠？要不要換更大的（2026-09-19 調查）

**VRAM 現況**：`rocm-smi` 確認這張是 **MI300X，192GB VRAM**，目前
`qwen2.5:7b-instruct` + `llava:7b` 兩個一起載入只用了 ~19.5GB，剩很多。
換更大的模型完全是 VRAM 允許的，純粹是下載時間跟推論速度的取捨。

**llava:7b 目前的問題不是跑不動，是「看不清楚小字」跟「prompt 故意寫得很
淺」**：實測拿一張模擬 VS Code 顯示 Python traceback 的截圖丟給現在部署的
prompt（一句話、不臆測），只回傳「編寫程式碼」，完全沒提到錯誤。換一個
要求「明確指出有沒有錯誤、錯誤類型」的 prompt，llava:7b 有注意到「有
traceback」，但把錯誤類型猜錯了（唸成 `NameError`，其實是 `KeyError`，
還憑空編出一個沒出現過的 `sklearn`）——這是 7B 級視覺模型讀小字終端機
文字常見的幻覺問題，不是量化或安裝設定的問題。

**已確認 Ollama library 裡存在、且 VRAM 裝得下的升級選項**（透過
`registry.ollama.ai` manifest API 直接查證，不是憑印象猜的）：

| 模型 | 用途 | 下載大小 | 備註 |
|---|---|---|---|
| `llama3.2-vision:11b` | 視覺 | 7.8 GB | 比 llava 新一代架構，OCR／細節描述通常明顯更準，**這是最推薦的視覺升級** |
| `llava:13b` | 視覺 | ~8 GB | 同代架構加大參數，進步有限 |
| `llava:34b` | 視覺 | 20.2 GB | 同代架構最大版，速度會慢不少 |
| `llama3.2-vision:90b` | 視覺 | 54.6 GB | 精度最高，但推論延遲會從秒級跳到明顯更久，比賽現場即時 demo 要先實測能不能接受 |
| `minicpm-v` | 視覺 | 需另查 | 以 OCR／文件理解見長的小模型，如果目標是「讀懂螢幕上的文字」這個特化方向可以考慮 |
| `qwen2.5:14b` / `qwen2.5:32b` | 文字 | ~9 / 19.9 GB | 摘要、affect-label 的語氣/精準度會更好，但延遲會變長 |
| `qwen2.5:72b` | 文字 | 47.4 GB | 更好，但一句話反映這種即時任務不見得需要這麼大 |

**建議**：先只換視覺模型成 `llama3.2-vision:11b`（下載小、換掉不麻煩），
文字模型（qwen2.5:7b-instruct）維持不動——`parse-timer`／`affect-label`
這種簡單任務 7B 已經夠準，換更大反而拖慢即時反應。換法：

```bash
ssh mi300 "OLLAMA_MODELS=/mlsteam/workspace/ollama-models ollama pull llama3.2-vision:11b"
```

拉完之後改 `main.py` 的 `VISION_MODEL` 環境變數（或 export
`VISION_MODEL=llama3.2-vision:11b` 再重啟 `restart_service.sh`），
兩個模型可以並存在 `ollama-models` 裡，隨時切換比較效果，不用整個重來。

**如果要讓 caption 真的去判斷「有沒有錯誤」**：光換模型還不夠，`main.py`
裡 `/events/screen` 的 prompt 現在故意寫得很淺（"No speculation"）；要改
成類似「明確指出是否有錯誤訊息、錯誤類型」的 prompt，這是程式碼改動，
不是模型選型問題——目前這份 repo 還沒做這個改動，需要的話我可以動手，
但要注意上面提到的幻覺風險，細節資訊建議展示時加一句「AI 描述僅供參考」
之類的免責態度，不要當成除錯工具本身在用。

# MI300 模型切換與實測紀錄

2026-09-19。此紀錄區分已驗證結果與背景工作；122B 尚無實測結論，下載／自動評測已依使用者要求暫停。

## 已部署

- 視覺：`qwen3.6:35b-a3b-q8_0`，Ollama digest `0218f872e86b`，模型檔約 38.7GB。
- 已驗證 100% GPU 載入，8K context 時 `ollama ps` 顯示模型約 37GB。
- `vision_think=false`、`vision_keep_alive="60m"`；文字模型仍為 `qwen2.5:7b-instruct`。
- 遠端設定：`/mlsteam/workspace/model-config.json`，格式如下，API 重啟時讀取。

```json
{"vision_model":"qwen3.6:35b-a3b-q8_0","vision_think":false,"vision_keep_alive":"60m"}
```

環境變數 `VISION_MODEL` 優先於設定檔；若改回 MiniCPM，配對改成 `vision_think:null`。
設定檔位於持久化區域；模型快取也仍在 `/mlsteam/workspace/ollama-models`。
程式碼發布分支為 **`feat/mi300-model-lab`**。目前 MI300 的服務先前是透過 SSH 手動部署，
不是這個功能分支觸發的 CI 部署。現有 workflow 只在推送 `deploy` 分支時執行；
後續須將此功能分支合併進部署版本，避免舊版覆蓋測試頁與模型設定功能。
原開發工作目錄仍在 `main`，功能分支使用獨立 Git worktree 整理，未包含 ESP32 的開發中改動。
README 前面的 MiniCPM 現況由本節取代。

## 同事取得程式碼與使用服務

需要這個 private GitHub repo 的存取權限。首次取得：

```sh
git clone --branch feat/mi300-model-lab https://github.com/EthelHsiao/2026-Meichu-Hackthon.git
```

已經 clone 的同事可先 `git fetch origin`，再 `git switch --track origin/feat/mi300-model-lab`
（自己的工作目錄有未提交改動時，先妥善保存）。模型權重與 runtime 設定位於 MI300，不包含在 Git 中。

如果只要上傳圖片測試，不必 clone。先取得自己的 MI300 SSH 存取權限、設定 `mi300` 別名，
再依下節建立 tunnel。每位同事都要在自己的電腦建立 tunnel；不要共用 SSH 私鑰。

## 開啟測試頁

本次已在使用者電腦建立本機 SSH tunnel，並開啟 Chrome 的測試頁：

http://127.0.0.1:18000/model-lab

若之後 tunnel 關閉，重新執行：

```sh
ssh -N -L 127.0.0.1:18000:127.0.0.1:8000 mi300
```

可選已安裝模型、上傳圖片、修改 prompt／JSON Schema、設定 token 上限與 thinking。
頁面使用 `POST /analyze/screen`，**不寫事件或記憶**；`GET /models` 列出已安裝模型。
API 的 `json_valid` 只表示 JSON 語法可解析。畫面顯示完整回應時間；TTFT 請用 `benchmark.py`。
測試模型的選擇不會修改 `/events/screen` 的預設模型。

## 已完成的合成圖片比較

資料均由 `run_suite.py` 人工生成，沒有使用或複製既有使用者截圖。
六張 1920×1080 PNG：TS2322、Python KeyError、ESLint、pytest 失敗、成功建置、文件內的錯誤範例。
相同 prompt／schema、temperature=0、seed=42、context=8192、輸出上限 768；Qwen thinking 關閉。
各模型一次 warmup，六張不同圖片各一次，再加兩次同圖重複。以下統計只用六次 distinct phase，
但其中第一張與 warmup 相同，可能命中快取。下載作業及既有背景摘要服務也仍在運作。

| 模型 | JSON Schema 合格 | 基本欄位檢查 | 完整回答中位數 | 最慢一張 |
| --- | --- | --- | --- | --- |
| MiniCPM-V | 6/6 | 17/20 | 7.35 秒 | 13.90 秒 |
| Qwen3.6 35B-A3B Q8 | 6/6 | 20/20 | 14.05 秒 | 17.19 秒 |

20 個檢查：每張 app；四張錯誤圖的類型、錯誤碼／exception 名、行號；兩張非錯誤圖沒有誤報。
**這不是整體準確率或「最強模型」排名**，也沒有量測 p95。

MiniCPM 的三個未通過項目：Python 行號、ESLint 規則名，以及將文件中的 KeyError 範例當成實際錯誤。
35B 可讀到 TS2322 的型別不相容原因，也能從可見字典找出缺少 `response` 鍵。
但 35B 在測試失敗案例的 cause 中，多推測了畫面未顯示的函式實作；基本欄位全對不代表根因全對。
後續應加強「只描述直接證據；未顯示的函式實作不得推論」的 prompt，並以真實截圖驗證。

正式 `/analyze/screen` 已實測預設使用 35B，約 14.44 秒讀出 runtime `KeyError: 'response'`、
`/workspace/client.py` 第 12 行及缺少字典鍵的原因。`error.code` 為 null、exception 位於 message，
若希望 exception 一律出現在 code，需在 schema／prompt 明確定義欄位。
既有 `ingest_screen` 兩段式摘要也用臨時 SQLite 實測成功，约 5.97 秒，沒有寫入正式記憶。

## 2026-09-19 上傳測試變慢的檢查與清理

當時 GPU 只載入 35B 與 7B，總顯存約 45.1 GiB／192 GiB，未發生顯存塞滿。
Ollama 紀錄顯示 07:24:40 UTC 開始重新啟動／載入 35B runner，到 07:25:54 才完成該次
請求；HTTP 約 73 秒，但圖片處理與生成約 18.18 秒。證據支持主要額外延遲是冷載入，
不能把整段等待稱為圖片上傳時間。122B 當時仍在下載，但沒有在 GPU 上推論。

已處理：

- 移除 `llava:7b`、`llava:34b`、`llama3.2-vision:11b`、`minicpm-v:latest`；目前只安裝 35B 與 7B。
- 暫停 122B 下載及自動評測，部分檔案保留供續傳。這些背景工作目前不會自行繼續。
- API 每次使用主視覺模型後保留 60 分鐘；非主模型的一次性圖片比較使用 `keep_alive=0`。
- 主模型保留時間可透過 `model-config.json` 的 `vision_keep_alive` 調整；`/health` 會顯示。

修正後的合成 Python 錯誤圖實測：完整回應 **15.62 秒**、模型載入 **0.009 秒**、
prompt 處理 1.71 秒、生成 13.51 秒（286 tokens）。`ollama ps` 確认保留時間約 59 分鐘。
這與使用者那張 73 秒圖片不是相同輸入，不能當作同圖前後速度倍率；它確認主模型已保持載入，
剩餘時間主要是生成回答。此次測試在 MI300 本機呼叫 API，沒有單獨量測使用者端上傳頻寬。

紀錄：`/mlsteam/workspace/model-eval/keepalive-smoke.json`。

## 122B 背景工作（已暫停）

`qwen3.5:122b`（模型檔約 81GB）曾開始下載，**目前已暫停、不是正式模型，也尚無結果**。
原先等待下載後自動評測的程序已停止。保留腳本與部分下載，但不會自動恢復。

遠端工作區：`/mlsteam/workspace/model-eval/`

- `qwen35-122b.status.json`：下載狀態；`qwen35-122b.pull.log`：下載進度。
- `evaluate_122b_when_ready.py`：原等待評測腳本，目前沒有執行。
- `qwen35-122b.eval.log`：推論紀錄，下載完成後才會產生。
- `qwen35-122b.summary.json`：評測完成後的摘要。
- `*.results.jsonl`：每次輸入參數、圖片 SHA256、原始回答與計時。

```sh
ssh mi300 "cat /mlsteam/workspace/model-eval/qwen35-122b.status.json"
ssh mi300 "cat /mlsteam/workspace/model-eval/qwen35-122b.summary.json"
```

之後需要恢復比較時，先跑 `ollama pull qwen3.5:122b` 續傳，再執行下列指令
（尚未產生同名 results 檔時）：

```sh
/mlsteam/workspace/model-eval/venv/bin/python /mlsteam/workspace/model-eval/run_suite.py --model qwen3.5:122b --label qwen35-122b --think off
```

## 驗證與還原

已驗證：隔離資料庫下的設定檔讀取、HTTP 路由、schema／thinking 參數、計時、原文字模型呼叫相容性；
JS 語法；Chrome 實際載入頁面並顯示 35B 預設模型；正式 API 真實图片推論；舊摘要流程。
瀏覽器檔案選擇器上傳流程未做自動端到端測試。

原始遠端程式備份：`/mlsteam/workspace/model-eval/backups/20260919T070638Z/`。
`/health` 新增 `app_sha256`，避免把手動部署的檔案誤認為完全等同 `deploy_sha` 所指的 Git commit。

MiniCPM 已依清理要求移除。如需退回，須先 `ollama pull minicpm-v` 重新下載，
再將設定檔的 `vision_model` 改成 `minicpm-v`、`vision_think` 改為 null，再執行：

```sh
bash /mlsteam/workspace/repo/mi300-deploy/deploy/restart_service.sh /mlsteam/workspace/repo
```

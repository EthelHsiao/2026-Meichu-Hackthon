# 模型選擇與 prompt＋截圖測試（2026-09-19）

最新部署與實測請看 [DEPLOYED_MODEL.md](DEPLOYED_MODEL.md)：現已切換 Qwen3.6 35B Q8，並提供 `/model-lab` 圖片測試頁。

後續清理：目前只安裝 35B 與 7B。下方 MiniCPM 命令保留作為歷史 baseline 範例，若要重跑需先重新下載；日常請使用 Qwen3.6 命令。122B 下載與自動評測已暫停。

## 建議先比較的組合

這是選型建議，**不是新模型在 PN54／MI300 上的實測排名**。
本次唯讀確認遠端為單張 MI300X（206141652992 bytes，約 192 GiB VRAM）、
Ollama 0.34.2。初次選型時已裝 minicpm-v、LLaVA 與 Qwen2.5 7B；後續部署進度另記於上方連結。

| 位置／用途 | 第一輪模型 | 選擇理由與限制 |
| --- | --- | --- |
| MI300 日常螢幕理解 | Qwen3.6-35B-A3B，先測 Q8_0 | MoE、支援圖片；適合評估視覺＋程式語意。總參數約 35B，每 token 啟用約 3B，不代表只需儲存 3B 權重。Ollama Q8_0 約 39GB；BF16 約 71GB，可加做精度比較。 |
| MI300 同級對照 | Qwen3.6-27B Q8_0 | Dense 模型，約 30GB 下載；用同一批小字與錯誤截圖決定是否更準。不能從參數量推論一定比 MoE 強。 |
| MI300 品質上限候選 | Qwen3.5-122B-A10B，先測 Ollama `qwen3.5:122b` | 官方 tag 約 81GB，有單卡容量空間；較大的 MoE，用來測疑難畫面是否改善。完整顯存還含 KV cache、視覺 encoder、工作區；無法只用下載大小保證長 context 或併發能跑。 |
| PN54 對話主候選 | Qwen3.5-9B Q4_K_M 等 4-bit 量化 | 本機只給文字：口述轉錄、檢索記憶、MI300 結構化情境。Ollama 9B tag 約 6.6GB，供容量參考；總 RAM 額外預留 OS、IDE、ASR、TTS、KV cache。 |
| PN54 低延遲對照 | Qwen3.5-4B 4-bit | 比較短句回覆品質與首字延遲，Ollama tag 約 3.4GB。9B 若不符合互動延遲目標，就選 4B。 |
| PN54 必須用 NPU 時 | AMD 發布的 Qwen3-8B Ryzen AI 量化版本；較輕量可測 Qwen3-4B | 依 Ryzen AI Software、OS 與硬體支援表安裝，不能把普通 GGUF 當成 NPU 模型。1.8 文件列有 Qwen3 8B／4B；Linux 文件明示不支援 Hybrid flow。 |

檔案大小是官方庫顯示的約數，不是執行峰值。32 GiB 系統 RAM 也不是 32 GiB 獨立顯存。
PN54 未確認 OS／NPU 必要性之前，先把 CPU 和 llama.cpp Vulkan iGPU 作為可測路線；
Lemonade 可管理這些 backend。實際要看 driver、GPU offload 日誌與資源使用量。
不建議第一輪就把約 24GB 的 35B 模型塞入 PN54，會壓縮其他常駐元件的記憶體空間。

MI300 沿用 Ollama 可最快開始。AMD 已發表 Qwen3.6 在 MI300X 上的 ROCm／vLLM 支援，
但這不等於目前 Ollama 的每個量化與視覺路徑都已通過驗證。先完成圖片＋JSON smoke test。
若要換 vLLM，需另配 ROCm 相容環境；現有 MLSteam basic pod 沒有 Docker，不要直接套用
需要 Docker daemon 的範例。不要把現有 `mllama` loader 失敗推廣成所有 MI300 都不能跑。

官方依據：

- [Qwen3.6 模型卡：圖片輸入、non-thinking 與模型架構](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
- [Ollama Qwen3.6 精度與大小](https://ollama.com/library/qwen3.6/tags)
- [Ollama Qwen3.5 各尺寸](https://ollama.com/library/qwen3.5)
- [AMD Qwen3.6／MI300X 支援](https://www.amd.com/en/developer/resources/technical-articles/2026/day-0-support-for-qwen3-6-on-amd-instinct-gpus.html)
- [Ryzen AI 1.8 模型清單](https://ryzenai.docs.amd.com/en/main/llm_list.html)
- [Ryzen AI Linux NPU 與 Hybrid 限制](https://ryzenai.docs.amd.com/en/latest/llm_linux.html)
- [Lemonade llama.cpp backend 支援](https://lemonade-server.ai/docs/guide/configuration/llamacpp/)

## 兩台機器如何分工

MI300：截圖 → VLM → 結構化 screen event。

PN54：語音 → ASR 文字 → 程式檢索記憶 → LLM（口述＋相關記憶＋近期 screen event）→ 短句 → TTS。

ASR／TTS 是另外的元件，不包含在本次 LLM 延遲中。PN54 此任務不必把圖片再次交給本機 VLM。
LLM 不會自動知道 SQLite 的內容。先由程式按 user_id、專案、時間與關鍵字篩選／檢索，再提供
少量相關記憶；之後需要語意搜尋時再加入 multilingual embedding 和向量檢索。
先採程式固定檢索，較容易測品質與控制延遲；必要時再讓模型以工具呼叫改寫查詢。

目前資料庫在 MI300，且只有最近事件／摘要，還沒有使用者分隔或語意檢索。
若目標是斷網也能使用記憶，需在 PN54 同步／保存記憶；本測試不變更這個架構。
screen event 應由程式補上 user_id、capture timestamp、request ID；不要讓模型編造這些 metadata。

單張截圖只能推論可見情境。看到錯誤訊息與知道真正根因是兩件事：
例如 KeyError 通常是 runtime error，而根因是否是上游回傳格式改變，需要程式或 log 證據。
`cause=null` 是合法結果。能從 OS 取到 foreground app、從 IDE 取到 diagnostics 時，
可一併使用確定性資料，VLM 著重理解畫面與關聯。

## 直接測 prompt＋圖片

`benchmark.py` 是獨立 Python 3.10+ CLI，僅使用標準函式庫，不會呼叫 `/events/screen` 或寫 memory.db。
支援任意 prompt、UTF-8 prompt 檔、圖片、schema、重複測試；原圖不縮小、不重壓縮。
需要自己提供截圖。模型需已安裝；腳本不會自動下載或切換正式服務設定。

在本機另一個終端開 tunnel（11435 避免與本機 Ollama 衝突）：

```sh
ssh -N -L 11435:127.0.0.1:11434 mi300
```

從 repo 根目錄先測已安裝 baseline，`screen.png` 換成你的檔案路徑：

```sh
python mi300-deploy/bench/benchmark.py --model minicpm-v --image screen.png --prompt-file mi300-deploy/bench/screen-prompt.txt --schema mi300-deploy/bench/screen-schema.json --warmup 1 --runs 5 --output mi300-deploy/bench/results/minicpm-v-01.jsonl
```

自行準備新候選時，在 MI300 終端依序下載／測試。先測第一個，避免一次下載所有候選：

```sh
ollama pull qwen3.6:35b-a3b-q8_0
# 接著才考慮 ollama pull qwen3.6:27b-q8_0
# 品質上限候選：ollama pull qwen3.5:122b
```

比較新模型（先关闭 thinking，減少固定格式擷取任務的額外延遲）：

```sh
python mi300-deploy/bench/benchmark.py --model qwen3.6:35b-a3b-q8_0 --image screen.png --prompt-file mi300-deploy/bench/screen-prompt.txt --schema mi300-deploy/bench/screen-schema.json --think off --runs 5 --output mi300-deploy/bench/results/qwen36-35b-01.jsonl
```

自由改 prompt、不限制 JSON：

```sh
python mi300-deploy/bench/benchmark.py --model minicpm-v --image screen.png --prompt "請逐字讀出終端機的錯誤訊息，不清楚的地方不要猜。" --runs 1 --output mi300-deploy/bench/results/prompt-02.jsonl
```

只測本機文字模型時，省略 `--image`、改 `--url http://127.0.0.1:11434`，prompt 檔放
使用者句子和固定的檢索記憶。此 CLI 只支援 Ollama native API；Lemonade／vLLM 的
OpenAI-compatible API 不能直接使用這個 CLI，需另外接對應 client。

## 看哪些數字

- `ttft_output_s`：HTTP 開始到第一個非空輸出片段，可能只是 thinking。
- `ttft_content_s`：到第一個非空正式回答片段；串流可能把數個 token 包在同一片段，這是 client 觀測值。
- `wall_s`：從送出 HTTP 到收到完成記錄，包含傳輸、等待、載入、推論；不包含讀檔與 base64 前處理。
- `load_duration_s`／`prompt_eval_duration_s`／`eval_duration_s`：Ollama 回報的階段時間。
  prefill 數字不能當成獨立的 vision encoder 精確時間。
- `decode_tokens_per_s`：Ollama output count / decode duration；開 thinking 時可能包含其 token。
- `response`／`thinking`／`parsed_json`：完整結果，便於比較 prompt。
- `json_valid`：**只代表 JSON 語法可解析**，不是 JSON Schema 驗證，也不代表內容正確。
  schema 已送給 Ollama 做 constrained output，正式整合仍要用 JSON Schema／Pydantic 驗證欄位。
- `done_reason=length`：可能截斷；應增加 `--max-tokens` 後重測，不能算作完整回答。

JSONL 保存 prompt、schema、模型清單及 digest、圖片 SHA256、參數、每次回答與 p50／p95。
圖片內容不寫入 JSONL，但 prompt 與回答可能包含個人資訊。使用新輸出檔名，既有檔案不覆寫。
預設一次 warmup，不列入 summary；warmup 不保證是冷啟動。真正冷啟動要在隔離測試時卸載模型後再測，
不要在多人使用服務時任意 `ollama stop`。腳本保留模型 10 分鐘，測試本身也會使用 GPU 資源。

同一圖片重複跑可能命中 image／prefix cache，只能代表重複輸入延遲。
也要用不同截圖測真實工作負載；5 次只適合 smoke test，p95 的正式比較至少收集數十至上百次。
若測 end-to-end，另量截圖、編碼、網路、檢索、ASR、TTS；不能把此處 decode tok/s 當作使用者等待時間。

API 依據：[Ollama generate](https://docs.ollama.com/api/generate)、
[Structured outputs](https://docs.ollama.com/capabilities/structured-outputs)。

## 公平的測試集與 prompt engineering

先固定模型、量化、輸出 schema、context=8192、max tokens=512、temperature=0、thinking off。
temperature=0 只是擷取任務的可重現起點，不保證正確，也不是 Qwen 所有任務的官方最佳參數。
若 reasoning 任務變差，要另外比較官方建議的 sampling，不能假設原本 MiniCPM 的最佳參數通用。

建議準備 30–50 張人工標註截圖，留一部分做未參與調 prompt 的驗證集：

1. 無錯誤正常編輯、瀏覽器文件、terminal 等，避免只測 VS Code／只測錯誤畫面。
2. TypeScript compile error、Python runtime error、lint、測試失敗、套件安裝／網路錯誤。
3. 小字、模糊、遮擋、多個視窗、歷史錯誤已修正，以及無法判定根因的例子。
4. 每張比較原尺寸 PNG、1920px、目前 1024px JPEG quality=60；另外測全圖＋錯誤區塊裁切。

分開評分 app、activity、error kind/code/message、檔名／行號、根因是否有證據、
沒有錯誤卻捏造的比例、JSON schema 合格率，以及 p50／p95 完整延遲。
不要僅憑一张 KeyError 截圖就決定模型。

可先設產品目標（不是實測保證）：螢幕事件完整 JSON p95 < 5 秒；PN54 在 ASR 結束後
1–2 秒內開始產生可播報回覆。若要固定每 5 秒更新，要量實際吞吐／queue；現有 watcher
是「請求完成後再 sleep 5 秒」，所以間隔其實是推論時間＋5 秒。

建議取代目前「英文短句→繁中 40 字」的流程，讓 VLM 直接輸出結構化欄位與原文證據，
再讓 PN54 的對話模型使用它。現在 max_tokens=96 和 40 字改寫會丟掉診斷細節。
先測 quality／latency 的取捨，再決定模型與精度，不用為了用滿 192 GiB 而把模型放到最大。

# 陪碼：工作情境記憶與取用實作計畫

日期：2026-09-19。交付範圍：架構、資料契約、建表草案、實作順序與驗收；本文件沒有修改或部署目前服務。

## 1. 決策與假設

先把使用者說的 BLM 理解為「讀取螢幕並產生描述的視覺模型」，以下稱 VLM；小龍蝦理解為 OpenClaw。即使上游其實是文字模型，只要輸出相同 observation 契約，下游設計不變。

**建議第一版延用 SQLite，建立可追溯的事件、問題歷程及即時狀態；每次回答固定帶入即時狀態，只有需要歷史時才搜尋。** 不需要先訓練 attention、不需要先部署獨立向量資料庫，也不需要把 OpenClaw 整套搬進來。

適用假設：目前為單一使用者／少量 demo 使用者、單一 API 寫入服務、截圖與模型部署沿用現況。多使用者仍須從第一天保留 owner、session、project 的隔離欄位。以下延遲、數量、保留天數、權重都是建議起始值，並非已量測的效能或論文最佳值。

產品要回答的核心問題：

- 現在在做什麼、哪個專案、哪個錯誤仍在出現？
- 這件事最早／最近何時被看到？有多少次真正的失敗執行？
- 使用者此刻是在表達煩躁，還是在要求技術協助？
- 以前有沒有可用的解法，使用者偏好怎樣的回應？

## 2. Retrieval 與 self-attention 的界線

從 DB 讀取指定 session 的 state，是資料讀取；用 embedding similarity 從大量紀錄選 top-k，是 retrieval。兩者都可由應用在背景自動執行，不必要求回答模型自己呼叫搜尋工具。

Self-attention 處理已進入模型的 token 表徵，不能自行看到外部 DB。一般生成介面也沒有「把某筆記憶的 similarity 直接改成內部 attention 權重」的通用參數。把 score 寫進 prompt 只是在提供額外文字，不保證模型會照數字分配注意力。[Transformer 原始論文](https://arxiv.org/abs/1706.03762)

因此，將「不需要 retrieval」拆成兩個可實作目標：

1. **即時陪伴不依賴語意搜尋**：把已更新的 working state 固定放進回答 context。
2. **歷史資訊自動取用**：由 context builder 依情境觸發搜尋，使用者不需要下搜尋指令。

若研究目的確實是可訓練的 memory attention，可另做 `softmax(qKᵀ / √d + bias)V` 的外部 memory reader。但它仍須取得 memory slots；加權向量也不能直接當作普通文字 API 的 context。需額外的投影／cross-attention／訓練介面，應等規則與檢索 baseline 出現可量測瓶頸後再評估。

## 3. 現有程式可沿用什麼

本機程式閱讀結果，不代表重新驗證遠端部署：

| 現況 | 限制 | 改造方向 |
| --- | --- | --- |
| `app/main.py` 已有 SQLite `events(id, ts, source, text)` | 沒有 session、錯誤結構、捕捉時間 | 新增 v2 observations，保留舊表遷移來源 |
| `/events/screen` 先產生英文，再壓成不超過 40 字繁中 | 錯誤碼、來源、時間證據可能丟失 | 結構化資料先驗證落地，短摘要只供顯示 |
| `state(key, value)` 存短摘要 | 無版本、新鮮度或明確狀態轉移 | 新增按 session 儲存的 working_state |
| 每 60 秒摘要最近 30 筆事件 | 高頻重複畫面會擠掉問題起點 | 程式增量更新 episode，摘要模型只潤飾 |
| `/analyze/screen` 支援 schema 實驗 | `json_valid` 只驗證 JSON 語法；且不寫記憶 | 正式 ingestion 加欄位、列舉值與語意檢查 |
| `bench/screen-schema.json` 有 app/activity/evidence/error/cause | 尚無 observation 與 hypothesis 的完整隔離 | 延用其欄位並擴充事件 envelope |
| `screen_watcher.py` 同步送出，完成後 sleep 5 秒 | 實際週期包含網路與推論，並非每 5 秒完成一次 | 在截圖當下記 captured_at，不用寫 DB 的時間代替 |

不要由舊的 40 字摘要回填精確重試次數、起始時間或錯誤根因；無法重建的資訊保留 unknown。

## 4. 記憶分層與主資料來源

| 層 | 儲存內容 | 更新方式 | 回答時如何使用 |
| --- | --- | --- | --- |
| Observation：觀察事件 | 螢幕可見內容、執行結果、使用者原話 | 事件到達就新增 | 必要時追查證據；不整批塞進 prompt |
| Episode：一段問題歷程 | 同一任務／錯誤的首次、末次、計數、狀態 | 由明確規則增量更新 | 當前 active episode 固定帶入 |
| Working state：即時記憶 | 当前專案、active episodes、最近互動、資料新鮮度 | 事件驅動更新 | 每次回答直接讀取 |
| Durable memory：長期記憶 | 已確認偏好、已驗證解法、重要決策 | 有價值且有證據時才寫 | 核心偏好固定載入；其他按需搜尋 |

資料庫是本應用的主資料來源；Markdown 是可選的檢視／匯出格式。不要同時讓 DB 與 Markdown 各自可寫卻沒有衝突處理。第一版若允許使用者編輯偏好檔，應明確走「匯入、校驗、產生新版本」流程。

例如：

```text
memory.db                  程式使用的事件、狀態與長期記憶
exports/USER.md             使用者確認過的互動偏好
exports/MEMORY.md           重要解法與決策的精簡匯出
exports/daily/2026-09-19.md  當日 episode 摘要
```

暫時煩躁放在短期互動中，不能據此建立「這個使用者很焦慮」的永久人格標籤。

## 5. 上游輸出契約

### 5.1 由客戶端／伺服器提供的 metadata

`event_id`、`owner_id`、`session_id`、`device_id`、`captured_at`、`received_at`、`capture_seq`、已確認的 `project_id`、`run_id` 都由程式提供，不要求 VLM 猜測。owner 來自伺服器身分驗證；project 由已知 workspace／IDE 訊號提供，沒有就 null。

以下為合成例子，非真實觀測：

```json
{
  "schema_version": 1,
  "event_id": "obs-demo-001",
  "session_id": "session-demo",
  "captured_at": "2026-09-19T06:00:00Z",
  "source": "screen",
  "observation": {
    "app": "VS Code",
    "activity": "editing_code",
    "surface": "terminal",
    "is_live_result": true,
    "error": {
      "kind": "compile",
      "code": "TS2322",
      "message": "Type 'string' is not assignable to type 'number'.",
      "file": "src/example.ts",
      "line": 18
    },
    "evidence": ["終端機顯示 TS2322 與上述型別訊息"],
    "uncertainty": []
  },
  "hypotheses": [],
  "run_id": null
}
```

`is_live_result=true` 只表示看起來是程式輸出區，不代表是剛執行的結果；舊 terminal 輸出仍可能留在畫面。文件中的錯誤範例應標為 `surface=documentation`，不建立真實失敗事件。

### 5.2 驗證規則

- 先做 JSON Schema／Pydantic 驗證，再寫入正式 observation。錯誤輸出至多修復一次；仍失敗就記錄解析失敗，不冒充成功事件。
- `error.code` 保留 TS2322、KeyError 等可搜尋識別符；exception 類型在 schema 明確定義，避免散落於 message。
- `cause`／根因推測改放 `hypotheses`，標示 evidence 與未確認狀態；不能自動升格為已驗證解法。
- 區分 `error=null`、看不到 terminal、畫面解析失敗；後兩者不能當成錯誤消失。
- confidence 若由模型自行填寫，只當未校準訊號；critical 判斷優先看来源、run_id、明確結果與證據。
- 畫面與歷史文字都當作資料，不能當成新的系統指令。入庫前遮罩 token、密碼等敏感片段；原始截圖沿用處理後丟棄。

## 6. Episode：讓「卡了多久」有依據

### 6.1 如何歸到同一問題

為候選錯誤建立版本化 issue key：

```text
hash(project_scope + build_target + error_kind + error_code
     + normalized_repo_relative_file + normalized_message)
```

行號、時間戳、執行 ID 等不穩定部分不作主要識別；但保留原始值。不得把有意義的變數名、不同 expected/actual 型別全部正規化掉。錯誤碼相同但專案／檔案不同，不直接合併。缺少足夠識別資訊時採保守 episode，不靠 embedding 自動把兩個問題當成同一個。

一個 session 可同時有多個 episode；working state 指出目前焦點。建表草案中的 observation.primary_episode_id 表達主要歸屬；若正式支援一次 build 多個錯誤的完整對應，再加 episode_observations 多對多表。

### 6.2 狀態機

| 狀態 | 意義 | 轉移依據 |
| --- | --- | --- |
| active | 目前仍在處理且證據夠新 | 新的相符觀察／執行事件 |
| paused | 切換工作、離開或觀察太久未更新 | 明確切換，或超過 freshness 門檻 |
| resolved | 有解決證據 | 相同專案、target、revision 的成功結果，或使用者明確確認 |
| abandoned | 使用者明確放棄此問題 | 使用者確認，不從沉默推論 |
| unknown | 重啟／中斷後無法確認 | 等待新證據 |

成功 compile 不能用來解決 runtime／test episode；另一個 branch 的成功也不能關閉目前問題。已 resolved 的錯誤後來再出現，建立新的 episode 並保留 previous_episode_id；不要把兩天合成連續卡住兩天。

### 6.3 四個不能混淆的數字

| 欄位 | 計算方式 | 可以怎麼說 |
| --- | --- | --- |
| observation_count | 相符畫面被觀察的次數 | 「最近幾次畫面都還有這個錯誤」 |
| confirmed_failure_runs | 有獨立 run_id 且失敗的執行數 | 「這段期間有 3 次建置失敗」 |
| observed_span_seconds | last_seen_at − first_seen_at | 「大約 18 分鐘前就看到了，剛才還在」 |
| active_seconds_estimate | 有活躍訊號的相鄰觀察區間累計 | 「這段時間似乎一直在處理」；標記估計 |

confirmed_failure_runs 為 null 代表沒有可計數的執行訊號；0 代表已啟用訊號且尚未觀察到失敗。若要說「重試」，需先辨識第一次執行，再計算後續 run，不能把失敗數直接叫重試數。

時間由程式計算，不交給 LLM 猜。以 captured_at 為事件時間、received_at 為接收時間，統一 UTC 儲存。可另保存客戶端 monotonic 時間與序號；偵測明顯時鐘偏移時降低時間可信度。

active_seconds_estimate 起始規則：只有前後兩筆都屬於同工作範圍、具有非 idle 訊號、間隔不超過 60 秒才累加。只有截圖時通常無法知道使用者是否真的在操作，active_seconds_estimate 應保留 null。失焦、休息、斷線或間隔太大一律不累計。

freshness 門檻可先用 60 秒，之後按實際 capture 間隔的 p95 調整。截圖推論有延遲，回答要標示「最新畫面多久以前」。超時後不持續延長「卡住時間」，也不宣稱錯誤仍在。

### 6.4 去重與亂序

- 同 event_id 的網路重送：idempotent，不重複寫入／計數。
- 同畫面再次捕捉：是新的觀察時間，可更新 last_seen；可省略重複大段文字，但不能抹掉時間證據。
- 同 run_id 的多張畫面：只算一次真實執行。
- 模型回應乱序：舊 captured_at 可補進歷史，但不能覆蓋較新的 working state。更新 reducer cursor、版本與狀態要在同一交易中處理。
- 服務重啟：從 DB 的 reducer cursor 重播未處理事件，舊 active state 先檢查 freshness。

## 7. 資料庫設計

附檔 `memory-schema-proposal.sql` 是可在獨立空白 SQLite 驗證的 DDL 草案。它使用新的表名，沒有刪除／改寫目前 events 與 state，但仍不是可直接套用正式資料的 migration。

| 表 | 主要欄位／責任 |
| --- | --- |
| memory_sessions | session、owner、device、開始／結束時間 |
| memory_observations | event id、seq、來源、事件時間、project、schema version、JSON 證據、run id |
| memory_episodes | issue key、project、狀態、起迄時間、觀察／執行計數、解決證據 |
| memory_working_state | session 的小型 JSON snapshot、版本、最後處理序號、新鮮度 |
| memory_items | 長期偏好／解法／決策，scope、有效期、版本、來源 episode |
| memory_evidence | 長期記憶與原始 observation 的來源關聯 |
| memory_embeddings | 第二階段才寫：記憶版本、模型、維度、向量與 content hash |

第一階段核心是前四張；偏好少量使用 memory_items。memory_evidence 在首次產生長期記憶時使用；embeddings 暫時空白即可。

資料庫運作原則：

- 單一 DB writer queue；短交易內寫 observation、更新 episode 與 working state。先在交易外完成 VLM 呼叫，避免長時間鎖住 DB。
- 每個連線開啟 foreign_keys；設定 busy_timeout。WAL 可改善讀寫並行，但仍只有一個 writer。[SQLite WAL](https://www.sqlite.org/wal.html)
- DB 必須由 API 所在主機管理，AI PC 經 API 存取；不把 SQLite 放在多人直接讀寫的網路共用磁碟。現有 `/mlsteam/workspace` 的底層檔案系統需確認；若是網路掛載，不能假定 WAL 適用。[SQLite WAL 限制](https://www.sqlite.org/wal.html)
- owner 與 session 對應由伺服器驗證；DDL 外鍵不等於完整租戶隔離，所有查詢、寫入、來源關聯都要驗證 owner。客戶端不能指定其他人的 owner_id。
- 程式要驗證 JSON 格式與跨欄位一致性；SQL CHECK 僅處理基本限制。
- 若有多個 API replica／持續寫入競爭，再評估 PostgreSQL；先量測需求，不為少量記憶新增一套服務。

## 8. 寫入流程與成本控制

```text
截圖／IDE／執行結果／使用者語句
  → 取得事件 ID、捕捉時間與可信 scope
  → 結構化解析、驗證、遮罩
  → observation 入庫
  → 規則 reducer 更新 episode 與 working state
  → 回答可直接讀取最新狀態
  → 背景按事件結束／重要變化產生長期記憶與索引
```

推薦事件優先順序：執行工具直接提供的 exit code、run_id、build target 是判斷執行結果的主要訊號；VLM 補充無法直接取得的 UI 與上下文。不要為了「知道編譯失敗」刻意放棄已有的程式訊號。

截圖可以先做變化偵測，低變化畫面送輕量 heartbeat。推論消費速度不足時使用有界佇列與 latest-frame 策略，合併尚未處理的舊截圖；使用者語句與真實 run result 不丟棄。若 vision 與回答共用推論資源，前景回答應有較高優先權。

只 embed 已整理的 episode 摘要、已確認偏好與解法，不對每張截圖 embed。摘要先用結構欄位模板，必要時再讓 LLM 潤飾；同一段摘要不要反覆摘要以免漂移。episode 結束也不代表已找到根因：僅有 build 成功時，resolution_text 可記「已成功建置」，不能編造修復操作。

## 9. 回答前的 context builder

### 9.1 快路徑：即時陪伴

使用者說「唉，好煩」時：

1. 取得該使用者當前 session 與工作 scope。
2. 讀 working state、active episodes，以及最近數輪對話；檢查 freshness。
3. 讀少量已確認的回覆偏好。
4. 意圖判斷為表達情緒且沒有詢問過去時，跳過歷史搜尋。
5. 將資料包交给回覆模型；先回應原話，再引用一個有依據的背景。

不要用「好煩」單獨去查向量資料庫，否則容易找回別天的煩躁紀錄，而漏掉現在的 TS2322。

建議 memory context 先設 1,200 tokens 上限：當前狀態與證據約 450、短期互動與偏好約 250、選配歷史最多 400、餘量 100。實際使用 tokenizer 計數，並計入模型總 context 預算；不可截掉 uncertainty 與 scope 欄位。

### 9.2 慢路徑：需要歷史時才搜尋

觸發例子：「上次怎麼修的？」、「這是不是昨天那個問題？」、「幫我處理這個錯誤」，或當前問題需要補充過往已驗證解法。

搜尋 query 由使用者原話、當前 project、error code、file、message、task description 一起構成；避免用猜測的 cause 當成既定事實。

1. **先 scope filter**：owner 必須相符；project 優先限制當前專案。全域偏好另外讀；只有明確標為 reusable 的解法才可跨專案，且仍限同 owner。project unknown 時只用該 session，不擅自扩大到全部專案。
2. **候選召回**：exact error code／issue key／file，加 keyword 全文搜尋；第二階段才加 embedding cosine top-20。
3. **合併**：可先用 RRF，`Σ 1/(60 + rank)`，再用新鮮度、證據品質與是否為已驗證解法排序。60 與 top-20 都是需驗證的初始參數。
4. **去重**：同一 episode 優先只留一筆，避免五張同樣的畫面占滿 context。
5. **選擇**：最多 3 筆短記憶，沒有足夠相關證據就回傳空；具體門檻由測試集校準。
6. **帶回原文與來源**：回覆模型收到短文字、日期、scope、狀態、evidence IDs，不只收到 embedding／score。

若想用 similarity 加權，可把各特徵校準到一致尺度後試驗：

```text
score = 0.45 × semantic + 0.25 × lexical
      + 0.20 × recency + 0.10 × evidence_quality
```

這是應用層排序提案，不是 self-attention，也不是已驗證最佳權重。BM25 與 cosine 原始值不可直接相加；SQLite FTS5 的 bm25() 數值方向也需注意。初期用 rank fusion 更容易避免尺度問題。[SQLite FTS5](https://www.sqlite.org/fts5.html)

recency 可以使用 `exp(-ln(2) × age / half_life)`；日常 episode 可先試 7 天 half-life，長期偏好與仍有效的解法不應僅因時間久就消失。是否過時還要看專案／版本適用性。相關性、新近性與重要性的組合可參考 Generative Agents，但該論文不是此應用效能的證明。[Generative Agents](https://arxiv.org/abs/2304.03442)

### 9.3 Embedding 與中文搜尋

- 選能處理繁體中文、英文與程式識別符的 embedding 模型；先用真實查詢測試，不在此計畫指定未評測的冠軍模型。
- embedding 文字模板保留原 error code／message，再加繁中任務摘要；不要把 TS2322 翻譯掉。
- 儲存 model ID、版本、dimensions、dtype、content hash；只有相同模型／版本與維度可互相比較。換模型就重建索引。
- 小規模可先從 SQLite 讀取同 scope 的向量，以正規化點積精確計算；是否需要專用向量索引，依記憶數、維度與 p95 實測決定。
- FTS5 預設分詞不能假定可處理中文詞界；先用結構欄位做 exact match，中文可用先斷詞的索引欄位。trigram 可支援子字串，但全文查詢小於三個字元不匹配，不適合直接搜尋「好煩」。[FTS5 tokenizer 文件](https://www.sqlite.org/fts5.html)
- embedding 失敗時回退 exact／keyword + working state，不能讓記憶服務故障阻止基本陪伴回答。

## 10. 完整示例：使用者說「真的好煩」

以下為合成時間線，時間以台北顯示：

| 時間 | 證據 | 程式處理 |
| --- | --- | --- |
| 14:00 | 畫面出現 TS2322 | 建立 active episode；失敗執行数未知 |
| 14:01–14:17 | 多次相符畫面 | 更新 last_seen 與 observation_count，不增加重試数 |
| 14:18 | 同錯誤仍可見 | observed span 約 18 分鐘 |
| 14:18:10 | 使用者說「真的好煩」 | 建立 utterance observation，先取得目前情境 |

給回覆模型的示意 context：

```json
{
  "current_task": "修改 TypeScript 程式",
  "active_issue": {
    "error_code": "TS2322",
    "observed_span_minutes": 18,
    "active_minutes_estimate": null,
    "confirmed_failure_runs": null,
    "status": "active",
    "evidence_ids": ["obs-demo-001", "obs-demo-018"]
  },
  "freshness": {"latest_screen_age_seconds": 10},
  "user_expression": {
    "text": "真的好煩",
    "interpretation": "可能是在表達當下挫折",
    "source": "user_utterance"
  },
  "response_policy": {
    "acknowledge_first": true,
    "offer_debugging_only_if_requested": true,
    "do_not_invent_retries_or_cause": true
  }
}
```

沒有充分執行訊號時，可以回：

> 剛才幾次畫面都還是那個 TS2322，反覆看到真的很煩。辛苦了，我在。

如果要提時間，應說「這個錯誤大約 18 分鐘前就出現了，剛才還在」，不要說「你已經努力除錯整整 18 分鐘」。若 working state 過期，則只回應使用者當下的話，或明確說「剛才看到」，不假裝知道目前畫面。

「先同理、是否提問或提供技術建議」可以是產品預設；只有使用者確認後，才記成他的長期偏好。MVP 由使用者開口觸發，不額外加入定時主動安慰；未來要主動提醒時再增加 quiet hours、冷卻時間與去重。

## 11. OpenClaw 值得借用的部分

官方文件說明：OpenClaw 以 Markdown 保存記憶，USER.md 偏向使用者偏好，MEMORY.md 保存整理過的長期資訊，日期檔保存日常紀錄；memory_search 搜尋，memory_get 讀指定內容。它不是把整個歷史永久放進模型的 attention。[OpenClaw memory overview](https://docs.openclaw.ai/concepts/memory)

官方搜尋文件也描述語意與 keyword 混合搜尋，以及時間、重要性與去重排序。這是可參考的 retrieval 做法，沒有因此免除資料取得。[OpenClaw memory search](https://docs.openclaw.ai/concepts/memory-search)

| 做法 | 本應用是否需要 | 判斷 |
| --- | --- | --- |
| 近期狀態與長期記憶分開 | 現在需要 | 即時陪伴與跨天回憶用途不同 |
| 精簡偏好固定載入 | 現在可做 | 避免每次問相同互動偏好 |
| Markdown 作主儲存 | 不優先 | 高頻時間事件、去重、交易與計數用 DB 較清楚 |
| Markdown 匯出 | 選配 | 方便人檢視與除錯 |
| hybrid search | 第二階段 | 歷史問題／解法召回有價值 |
| 背景整理長期記憶 | 第二階段 | 優先整理已结束且有價值的 episode |
| 自訓 attention、圖資料庫、多 agent memory | 暫緩 | 目前沒有證據顯示是必要瓶頸 |

要在已安裝的 OpenClaw 中理解其行為，可以參考這些官方命令；本次沒有安裝或執行 OpenClaw：

```sh
openclaw memory status
openclaw memory index
openclaw memory search --query "TS2322 型別不相容" --max-results 5
```

status 檢視狀態、index 建索引、search 搜尋。它們是 OpenClaw 命令，不是你的 API 已有功能；實際 flags 應依安裝版本核對。[OpenClaw memory CLI](https://docs.openclaw.ai/cli/memory)

## 12. 實作順序與現有 API 對接

| 階段 | 具體工作 | 完成條件 |
| --- | --- | --- |
| P0：觀察契約 | 定義 observation schema；客戶端捕捉時間／event_id；正式 ingestion 結構驗證 | 真實錯誤、文件範例、無終端畫面能區分 |
| P1：即時記憶 MVP | 前四張表、episode reducer、freshness、scope、重送與重啟處理 | 不開 embedding，也能理解「好煩」發生的背景 |
| P2：回答串接 | context builder、已確認偏好、回答證據規則 | 回答可追溯，數字不超出證據 |
| P3：歷史召回 | episode 摘要、memory_items、exact/FTS；測試需要時再加 embedding | 能找回同專案過往已驗證解法，無匹配能留空 |
| P4：維運與擴充 | 清理、刪除重建、效能統計、多使用者隔離檢查 | 有可量測品質與延遲，再決定是否擴大基礎建設 |

推薦模組：`memory/models.py`（契約）、`store.py`（交易）、`reducer.py`（狀態機）、`context.py`（context 組裝）、`retriever.py`（選配搜尋）、`consolidate.py`（長期記憶整理）。這些只是待實作規劃，尚未新增模組。

API 建議：

- 保留 `/analyze/screen` 作無狀態測試，不悄悄寫正式記憶。
- `/events/screen` 增加捕捉 metadata 與結構化解析；可兼容舊呼叫，舊資料標記時間精度未知。
- `/events/note` 區分 utterance、run_result、task_switch；run_result 要由可信生產者提交，不能由任意文字冒充。
- `/status` 保留既有 dashboard 欄位，新增 working_state、freshness、active_episodes；summary 由結構狀態生成。
- 新增內部 `build_context(owner, session, utterance)`，可視需要曝露 `/memory/context`，再接到對話生成流程；現有程式尚無此完整對話路徑。
- 歷史搜尋與 embedding 在回答前只於必要時呼叫；不等待每 60 秒的背景摘要才更新目前情境。

遷移：先備份目前 DB；以獨立 DB／shadow mode 寫入 v2；在合成重播與真實樣本確認後再切換讀取路徑。舊 events 可匯為 legacy observation，但不得推造 session、run 或精確 active duration；舊 state 不視為真相來源。使用 PRAGMA user_version／migration ledger 管理版本，保留回退到舊讀取路徑的能力。

## 13. 驗收與評估

先建立 20–30 段有標註的合成時間線，再加經使用者同意的真實樣本。離線 replay 時每一回合只能看到當時已到達的資料，避免未來事件洩漏。驗收場景：

1. 同一張錯誤畫面重複 100 次：可以累計觀察，不能說重試 100 次。
2. 真正三次不同 run 的失敗：正確計數且重送不加倍。
3. 文件內的 TypeError 範例：不建立實際失敗 episode。
4. 切去吃飯 20 分鐘再回來：不把空白時間算成持續工作。
5. 同專案 compile 成功：只解決相符 scope 的 compile issue，不抹掉測試失敗。
6. 兩個專案同 TS2322：保持分開；跨 owner 一律不可取到。
7. 舊畫面晚到／服務重啟：不覆蓋新狀態，不重複計數。
8. 使用者只說「好煩」：使用當前背景，不隨意引用昨天情緒。
9. 問「上次怎麼修」：召回來源與版本相符的解法；無證據不編造。
10. 偏好更新／刪除：舊偏好不再生效，cache、FTS、embedding、匯出同步清理。
11. embedding 不可用：基本狀態與陪伴回覆仍可運作。
12. VLM 編造 cause：不寫成已驗證根因或永久解法。

量測：

| 指標 | 驗收方向 |
| --- | --- |
| 錯誤／episode 對應 | 與人工標註比對 precision、recall |
| 計數、時間、狀態機 | 合成案例全部符合規則，沒有數字幻覺 |
| 回答 groundedness | 所有具體錯誤碼、時間、次數可追到 evidence |
| 歷史 retrieval | relevant Recall@3、Precision@3、無答案時的錯誤召回率 |
| scope 隔離 | 測試集零跨 owner 洩漏；跨 project 只依明確策略 |
| 延遲 | 分開量 capture、VLM、reducer、context build、生成 TTFT；記 p50/p95 |
| 使用體驗 | 使用者評分：背景是否正確、是否煩人、是否適時、有沒有過度建議 |

context build 可先以快路徑 p95 < 100ms、歷史搜尋 p95 < 300ms 為工程目標；不含 VLM／語音／回答生成時間，需在目標機器驗證。回應時延可能主要來自模型推論，而不是 SQLite。

比較三個版本：A 只有最近對話；B 對話 + episode/working state；C B + 歷史 hybrid retrieval。若 B 已滿足即時陪伴，C 僅改善歷史題目，就讓搜尋保持選配，不把更複雜當成更好。

## 14. 保留與刪除策略

初始提案：原始截圖不落地；結構 observation 保留 7 天，episode 摘要保留 30 天，已確認偏好保留到撤回／變更；真正有價值的解法另定有效期。上述天數需按使用者需求與測試調整。

到期清理 observation 前，保留最小的已遮罩證據摘要與原始來源 metadata，或將依賴它的 memory 標為來源已過期；不能让來源消失後仍聲稱可完整追查。使用者要求忘記某段資料時，按 evidence lineage 找到受影響的摘要、向量、FTS、working state 與 Markdown 匯出，刪除或重新生成；日後重播不得把它復活。備份採既定到期淘汰政策，說明刪除何時涵蓋備份。

工程追蹤只記必要事件 ID、使用到的 memory ID、版本、取用原因與延遲；不額外無限保存完整畫面文字或每次回答 prompt。

## 15. 此刻最值得先完成的交付

第一個可 demo 的里程碑是：**即使沒有向量搜尋，系統也能根據有來源的當前 episode，對「好煩」給出準確、簡短的情境回應。**

先完成 observation schema、episode reducer、working state 和 context builder；把 embedding 留給「上次怎麼修」等已知有需求的歷史題目。這樣每一個增加的元件都有可驗證的用途。

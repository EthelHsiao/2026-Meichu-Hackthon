# Memory

桌寵的記憶放在 AIPC 上的一個 SQLite 檔案：`ai-pc-agent/data/memory.db`。
程式在 `ai-pc-agent/memory/`，參數在 `ai-pc-agent/config.py`。

## 截圖 → 記憶

```
AIPC 收集 observation + 截圖 ──▶ VLM ──▶ {"text", "error"} ──▶ store.py 加工 ──▶ memories 一列
```

**VLM 的輸入**（B 的 observation，`observation_models.py`）：

```json
{
  "observation": {
    "observation_id": "uuid",
    "timestamp": "2026-09-19T09:20:00+08:00",
    "foreground": {"app": "code", "window_title": "main.py - VS Code", "workspace": null},
    "system": {"running_apps": ["code", "chrome"], "idle_seconds": 4},
    "screen": {"screenshot_path": "...", "image_sha256": "...", "perceptual_hash": "..."},
    "enrichments": {"git": null, "vscode": null, "browser": null, "terminal": null}
  },
  "image_b64": "截圖（JPEG）"
}
```

- 不放記憶：VLM 只描述「這張截圖此刻在做什麼」

**VLM 的輸出**（只有描述）：

```json
{"text": "在 main.py 遇到 KeyError", "error": "KeyError: 'response'"}
```

- `error`：畫面上看得到錯誤才填，否則 `null`
- 時間、id、合併、embedding 都不由 VLM 回傳，交給 `store.py`

**`store.py` 加工**（`agent.py` 的 `memory_fields()`）：

- `ts`：observation 的 `timestamp`
- `app`：`foreground.app`
- `error_sig`：`error` 冒號前面那段，例如 `KeyError`
- `state_key`：`app|視窗標題|error_sig`，跟上一筆一樣就只延長時間
- 接著算 embedding、決定重要度、寫進 `memories`

## 兩張記憶表

### `memories`：發生過的事

一列 = 一件事。分兩種（`level` 欄位）：

- **raw**：最近發生的事，細節完整
  - 來源：截圖、使用者說的話、桌寵說的話、觸覺
  - 狀態沒變（同一個 app + 視窗 + 錯誤）就不新增，只延長結束時間 → 一件事只有一筆
  - 衰減：半衰期 **3 天**
- **summary**：raw 超過 **24 小時**後，LLM 按時段整理成一句摘要，原本的 raw 刪掉
  - 衰減：半衰期 **30 天**
  - 永久保留，除非使用者手動刪除

例子：

```
raw      [09:20–10:00，40 分鐘] 在 main.py 遇到 KeyError
raw      [10:00–10:35，35 分鐘] 看 YouTube
raw      [10:36] 使用者說「好無聊」
            ↓ 24 小時後
summary  9/19 早上開發 API，被 KeyError 卡 40 分鐘，之後看 YouTube 休息
```

欄位（定義在 `memory/schema.sql`）：

- `ts_start`、`ts_end`：時間範圍，持續多久 = `ts_end - ts_start`
- `level`：`raw` 或 `summary`
- `source`：`screen` 截圖、`speech` 使用者說的話、`reply` 桌寵說的話、`touch` 觸覺、`summary` 摘要、`homework` 作業拍照分析（見 api.html §⑥）
- `app`：哪個程式，例如 `code`
- `state_key`：判斷狀態有沒有變，例如 `code|main.py|KeyError`
- `text`：記憶本體（一句話），也是唯一送進 prompt 的東西
- `error_sig`：錯誤類型，例如 `KeyError`
- `importance`：搜尋時的加權
- `embedding`、`embed_model`：`text` 的向量和算它的模型，只用來搜尋

### `profile`：使用者這個人

一列 = 一個穩定的事實，例如「在做 ESP32 桌寵專案」「習慣晚上寫 code」。

- 來源：使用者說「記住…」，或壓縮時 LLM 自己學到的（自動學習還沒寫）
- 不衰減，每次都整份放進 prompt

## 另外兩個不是記憶的東西

- `settings`：系統狀態，例如是否暫停記錄、上次壓縮時間
- `memories_fts`：搜尋用的索引，自動同步，不用管

## 回答問題時怎麼用記憶

prompt 裡放三段：

- **使用者檔案**：`profile` 全部
- **最近狀態**：`memories` 最新 10 筆
- **相關記憶**：用 RAG 從 `memories`（raw + summary 一起）搜出最相關的 5 筆

RAG 分數 = (0.7 × 語意相似度 + 0.3 × 關鍵字比對) × 時間衰減 × 重要度

- 語意相似度：embedding 向量的 cosine
- 關鍵字比對：BM25，負責 `KeyError`、`main.py` 這類精確字串
- 時間衰減：過了一個半衰期，分數剩一半
- 重要度：使用者說的話 1.5、有錯誤的記錄 +0.3、其他 1.0

## 刪除

- 自動：只有壓縮會刪 raw，而且是摘要寫入成功之後才刪
- 手動：刪某段時間（例如不小心截到敏感畫面）、全部清除
- 截圖本身從來不存，只存文字

## 目前完成度

- ✅ 資料表、寫入合併、RAG 搜尋、壓縮、手動刪除（有測試）
- ✅ 截圖 → 記憶：AIPC 端、MI300 端（`/v1/screen-observations`）都寫好了，還沒在真的 MI300/ESP32 上跑過端到端
- ✅ 語音、桌寵回覆、觸覺、作業拍照 → 記憶：`ai-pc-agent/main.py` 已經接好呼叫 `store.add_or_extend()`，還沒實機驗證
- ❌ profile 自動學習：要先決定用哪個 LLM
- ✅ 壓縮的背景排程：`main.py` 的 `_compaction_loop` 定時呼叫 `run_compaction()`，摘要器目前是陽春的字串接合（`naive_summarize`），要換成真的 LLM 摘要時直接替換那個函式就好
- ⚠️ embedding 模型（bge-m3）：測試用假模型，還沒在 AIPC 上實際跑過

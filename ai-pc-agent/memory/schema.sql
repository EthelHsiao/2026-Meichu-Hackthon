-- 記憶資料庫（SQLite，一個檔案：data/memory.db）
-- 分層參考 OpenClaw：profile ≈ USER.md（永遠放進 prompt、不衰減）、
-- raw ≈ 每日筆記（快速衰減）、summary ≈ MEMORY.md（壓縮後的長期記憶、慢衰減）

-- ① 原始記錄 + 摘要
CREATE TABLE IF NOT EXISTS memories (
  id          INTEGER PRIMARY KEY,
  ts_start    TEXT NOT NULL,      -- 開始時間（ISO 8601，含時區）
  ts_end      TEXT NOT NULL,      -- 結束時間；狀態沒變就只更新這欄
  level       TEXT NOT NULL,      -- 'raw' | 'summary'
  source      TEXT NOT NULL,      -- 'screen' | 'speech' | 'reply' | 'touch' | 'summary' | 'homework'
                                   -- ('homework'：FSR1 雙擊拍照分析作業流程，見 docs/api.html §⑥；
                                   --  自由文字欄位，沒有 CHECK constraint，加新值不用 migration)
  app         TEXT,               -- 'Code.exe'
  state_key   TEXT,               -- 判斷「狀態有沒有變」的 key（例如 app+視窗標題+錯誤），相同就延長不新增
  text        TEXT NOT NULL,      -- 真正的記憶內容（一句話）
  error_sig   TEXT,               -- 'KeyError' 之類，方便 SQL 精確查
  importance  REAL NOT NULL DEFAULT 1.0,  -- 搜尋時的加權，依 source / 有無錯誤決定
  embedding   BLOB,               -- float32 向量（numpy .tobytes()）
  embed_model TEXT                -- 算這個向量用的模型，換模型時知道要重算哪些
);
CREATE INDEX IF NOT EXISTS idx_memories_level_ts ON memories(level, ts_end);

-- BM25 全文索引。trigram tokenizer 才切得動中文（預設 tokenizer 會把整串中文當一個詞）。
-- 限制：少於 3 個字的查詢詞比對不到，所以 BM25 主要負責 KeyError、檔名這類精確字串，
-- 中文語意交給向量搜尋。
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
  text, content='memories', content_rowid='id', tokenize='trigram'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF text ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, text) VALUES ('delete', old.id, old.text);
  INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;

-- ② 使用者檔案：穩定的事實（「在做 ESP32 桌寵專案」），每次都放進 prompt、不衰減
CREATE TABLE IF NOT EXISTS profile (
  id         INTEGER PRIMARY KEY,
  fact       TEXT NOT NULL UNIQUE,
  source     TEXT,                -- 'user'（使用者說「記住…」）| 'extracted'（從對話擷取）
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- ③ 其他狀態：paused、last_compaction 等
CREATE TABLE IF NOT EXISTS settings (
  key   TEXT PRIMARY KEY,
  value TEXT
);

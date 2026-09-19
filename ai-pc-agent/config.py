"""AIPC 端所有可調參數集中在這裡。"""

# ---- ESP32 ----
SERIAL_PORT = "COM5"          # 依裝置管理員實際看到的改
SERIAL_BAUD = 115200          # 要跟 esp32-bringup/include/board_config.h 的 MONITOR_SPEED 一致

# ---- MI300 ----
MI300_BASE_URL = "http://localhost:8000"   # 透過 ssh -L port forward

# ---- 截圖 ----
SCREEN_INTERVAL_S = 20

# ---- 記憶 ----
DB_PATH = "data/memory.db"
EMBED_MODEL = "BAAI/bge-m3"
RECENT_N = 10                 # 【最近狀態】放幾筆
RAG_TOP_K = 5                 # 【相關記憶】放幾筆

# ---- RAG 打分：(W_VECTOR*cosine + W_TEXT*BM25) × 時間衰減 × importance ----
W_VECTOR = 0.7                # 起始值，實測後再調
W_TEXT = 0.3
RAG_CANDIDATES = 50           # 向量、BM25 各取前幾名進入合併
HALF_LIFE_DAYS = {"raw": 3, "summary": 30}   # 過了這麼多天分數剩一半；profile 不衰減
IMPORTANCE = {"speech": 1.5, "reply": 1.0, "screen": 1.0, "touch": 0.8, "summary": 1.2}
ERROR_IMPORTANCE_BONUS = 0.3  # 有 error_sig 的記錄額外加分

# ---- 寫入合併 / 壓縮（數值待定）----
SESSION_GAP_MIN = 30          # 活動中斷多久算下一個時段；同狀態但中斷太久也會開新的一筆
COMPACT_AFTER_HOURS = 24      # raw 超過多久才壓縮；demo 可調成 0.2
COMPACT_CHECK_EVERY_MIN = 60

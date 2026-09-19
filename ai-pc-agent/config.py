"""Environment-backed defaults for the AI-PC tracker."""

import os


def _float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


LOCAL_POLL_SECONDS = _float("LOCAL_POLL_SECONDS", "10")
SCREENSHOT_SECONDS = _float("SCREENSHOT_SECONDS", "30")   # 約每 30 秒截圖一次，對齊「約 36 秒」的需求
MIN_VLM_SECONDS = _float("MIN_VLM_SECONDS", "60")
IDLE_THRESHOLD_SECONDS = _float("IDLE_THRESHOLD_SECONDS", "60")
SCREENSHOT_DIR = os.getenv("SCREENSHOT_DIR", "./screenshots")
RETRY_QUEUE_SIZE = int(os.getenv("RETRY_QUEUE_SIZE", "20"))
"""AIPC 端所有可調參數集中在這裡。"""

# ---- ESP32（主板：FSR/IMU/LCD/蜂鳴器/麥克風，經 WebSocket，見 sensing/esp32_ws_client.py）----
ESP32_WS_URL = os.getenv("ESP32_WS_URL", "ws://192.168.4.1:81/api/v1/stream")
ESP32_WS_RECONNECT_SECONDS = _float("ESP32_WS_RECONNECT_SECONDS", "2")

# ---- ESP32-CAM（副板：拍照流程隨選拉取，見 chatgpt_bridge.py / main.py 的 homework 流程）----
ESP32_CAM_BASE_URL = os.getenv("ESP32_CAM_BASE_URL", "http://192.168.4.2")

# ---- 倒數頁面（debug_api.py 的 /homework-countdown，見 countdown_html.py）----
# 這是 debug_api:app 自己服務的頁面，所以網址要對應它實際跑的 host:port
# （目前部署固定用 8090，見 ai-pc-agent/deploy/ai-pc-agent-dashboard.service）。
HOMEWORK_COUNTDOWN_URL = os.getenv("HOMEWORK_COUNTDOWN_URL", "http://localhost:8090/homework-countdown")

# ---- STT（本機服務，見 sensing/stt.py）----
STT_WS_URL = os.getenv("STT_WS_URL", "ws://127.0.0.1:8765/ws/audio")

# ---- MI300 ----
MI300_BASE_URL = os.getenv("MI300_API", "http://localhost:8000")   # 透過 ssh -L port forward
MI300_SCREEN_OBSERVATION_PATH = os.getenv("MI300_OBSERVATION_PATH", "/v1/screen-observations")
MI300_CHAT_PATH = os.getenv("MI300_CHAT_PATH", "/v1/chat/completions")
MI300_HOMEWORK_PATH = os.getenv("MI300_HOMEWORK_PATH", "/v1/homework-analyses")

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
# source 除了下面列出的，還有 'homework'（FSR1 雙擊拍照分析流程，見 docs/api.html §⑥）
IMPORTANCE = {"speech": 1.5, "reply": 1.0, "screen": 1.0, "touch": 0.8, "summary": 1.2, "homework": 1.5}
ERROR_IMPORTANCE_BONUS = 0.3  # 有 error_sig 的記錄額外加分

# ---- 寫入合併 / 壓縮（數值待定）----
SESSION_GAP_MIN = 30          # 活動中斷多久算下一個時段；同狀態但中斷太久也會開新的一筆
COMPACT_AFTER_HOURS = 24      # raw 超過多久才壓縮；demo 可調成 0.2
COMPACT_CHECK_EVERY_MIN = 60

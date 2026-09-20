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
# ⚠ 網路：ESP32-CAM 只會加入外部熱點（STA），電腦又不能同時連兩個 WiFi，所以 demo 時
#   主板也要改 STA（esp32-bringup/include/telemetry_local.h 設 TELEMETRY_USE_STA 1），三台連
#   同一個熱點，再用環境變數 ESP32_WS_URL / ESP32_CAM_BASE_URL 填各自拿到的 IP：
#   ESP32_WS_URL=ws://esp32-companion.local:81/api/v1/stream
#   ESP32_CAM_BASE_URL=http://esp32-cam.local
# （兩塊板子的韌體都已經加了 mDNS，開機連上熱點後就會廣播這些名字；如果這台
# 電腦連不到 .local 網址，先確認有裝 avahi-daemon：sudo apt install avahi-daemon
# libnss-mdns，裝完通常不用重開機就能用；還是不行的話退回查 Serial Monitor
# 印出的實際 IP，直接填 IP 版本的網址。下面的預設值只適用「主板 SoftAP、不用
# 相機」的情況。）
ESP32_WS_URL = os.getenv("ESP32_WS_URL", "ws://192.168.4.1:81/api/v1/stream")
ESP32_WS_RECONNECT_SECONDS = _float("ESP32_WS_RECONNECT_SECONDS", "2")
ESP32_STREAM_FLUSH_SECONDS = 0.1   # 台詞串流時多久合併送一次（太頻繁會塞爆 ESP32）

# ---- 手勢判斷（AIPC 從 ESP32 每 50ms 一包的 telemetry 原始數值判斷，見 sensing/gestures.py）----
# 調的方法：接上 ESP32 後跑
#   python -m sensing.gestures --live
# 實際做每個動作，看印出來的數值再改這裡（不用重燒韌體）。
FSR_PRESS_RAW = 250           # [CONFIRMED] 12-bit ADC（0~4095），超過算「有壓」；2026-09-20 拿
                               # receive_telemetry.py 實測校準過，跟韌體 FSR1_PRESS_THRESHOLD 同步
SQUEEZE_MIN_MS = 500          # 兩個 FSR 同時壓住多久算「捏」
PAT_MAX_MS = 250              # 單一 FSR 壓一下、多短就放開算「拍」
PAT_CONFIRM_MS = 600          # 拍完等多久沒有第二下才確定是拍（FSR1 第二下 = 韌體會送 double_tap）
SHAKE_WINDOW_MS = 800         # 看最近多久的加速度
SHAKE_ACCEL_P2P = 10.0        # m/s²：視窗內 |加速度| 最大減最小超過這個算「搖」（靜止時約 9.8、幾乎不變）
SHAKE_COOLDOWN_MS = 2000      # 搖完多久內不再重複送
STILL_GYRO = 0.3              # rad/s：角速度比這小算沒在轉
STILL_ACCEL_DEV = 1.0         # m/s²：|加速度| 跟 9.8 差這麼多以內算沒在動
REST_MIN_MS = 1500            # 靜止多久算「放下了」
MOVE_MIN_MS = 300             # 從靜止開始連續動多久算「拿起來了」

# ---- ESP32-CAM（副板：拍照流程隨選拉取，見 chatgpt_bridge.py / main.py 的 homework 流程）----
# 同上，共用熱點模式下改用環境變數覆蓋：ESP32_CAM_BASE_URL=http://esp32-cam.local
# （esp32-cam-bringup/src/main.cpp 也已經加了對應的 mDNS，名字是 esp32-cam）。
ESP32_CAM_BASE_URL = os.getenv("ESP32_CAM_BASE_URL", "http://192.168.4.2")

# ---- 倒數頁面（debug_api.py 的 /homework-countdown，見 countdown_html.py）----
# 這是 debug_api:app 自己服務的頁面，所以網址要對應它實際跑的 host:port
# （目前部署固定用 8090，見 ai-pc-agent/deploy/ai-pc-agent-dashboard.service）。
HOMEWORK_COUNTDOWN_URL = os.getenv("HOMEWORK_COUNTDOWN_URL", "http://localhost:8090/homework-countdown")
HOMEWORK_TRIGGER_COOLDOWN_SECONDS = _float("HOMEWORK_TRIGGER_COOLDOWN_SECONDS", "3.0")

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

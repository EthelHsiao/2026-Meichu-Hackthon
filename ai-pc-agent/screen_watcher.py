"""
在 AI PC 上跑的背景截圖程式——每隔 INTERVAL_SECONDS 秒截一次主螢幕，
縮小＋壓縮後傳給 MI300 的 /events/screen，MI300 端轉成文字描述後即丟棄圖片本體，
落地只留文字（見 mi300-deploy/app/main.py 的說明與隱私設計）。

用法：
    ssh -N -L 8000:localhost:8000 mi300 &     # 先開 port forward
    pip install -r requirements.txt
    python screen_watcher.py

也可以呼叫 send_note() 把使用者口述或 agent 狀態變化，直接送一句話進記憶
（不用截圖），對應 mi300-deploy/app/main.py 的 /events/note。
"""
import base64
import io
import time

import mss
import requests
from PIL import Image

MI300_API = "http://localhost:8000"  # 透過 ssh -L port forward 打過去
INTERVAL_SECONDS = 5
MAX_WIDTH = 1024        # 截圖縮小到這個寬度以內，減少傳輸量跟 vision model 延遲
JPEG_QUALITY = 60


def capture_and_send():
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # 主螢幕；多螢幕的話依需求改索引
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        img = img.resize((MAX_WIDTH, int(img.height * ratio)))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    resp = requests.post(f"{MI300_API}/events/screen", json={"image_b64": image_b64}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def send_note(text: str, source: str = "utterance"):
    resp = requests.post(f"{MI300_API}/events/note", json={"text": text, "source": source}, timeout=10)
    resp.raise_for_status()
    return resp.json()


if __name__ == "__main__":
    print(f"[screen_watcher] 每 {INTERVAL_SECONDS} 秒截圖一次，打到 {MI300_API}")
    while True:
        try:
            result = capture_and_send()
            print(f"[screen_watcher] {result.get('ts')}  {result.get('caption')}")
        except Exception as exc:  # noqa: BLE001 — demo 用的常駐迴圈，單次失敗不該讓整個程式掛掉
            print(f"[screen_watcher] 失敗，略過這輪: {exc}")
        time.sleep(INTERVAL_SECONDS)

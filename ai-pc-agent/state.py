"""「此刻」的情境快照，只放記憶體、不存檔。每次截圖、觸覺事件都會更新。"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class ContextState:
    app: str = ""                          # "Code.exe"
    window_title: str = ""                 # "main.py - backend - VS Code"
    activity: str = ""                     # 截圖整理出來的一句話
    activity_since: Optional[datetime] = None
    error: Optional[str] = None            # "KeyError: 'response'"
    error_since: Optional[datetime] = None # now - error_since = 卡了多久
    last_touch: Optional[dict] = None      # 最近一次觸覺事件
    last_touch_ts: Optional[datetime] = None  # 上面那次觸發的時間，判斷手勢是不是剛剛才發生的
    last_telemetry: Optional[dict] = None  # 最近一筆原始 FSR/IMU 數值，只給 dashboard 即時顯示
    last_mic_ts: Optional[datetime] = None  # 最近一次收到 ESP32 麥克風 frame 的時間，判斷音訊有沒有在傳
    mic_frames_total: int = 0               # 從程式啟動累計收到幾個麥克風 frame（debug 用，不是精確計數器）
    last_stt_level: Optional[dict] = None   # STT 服務最新回報的 {rms, peak, vad, ...}，只給 dashboard 即時顯示
    lcd_expr: str = "idle"                  # LCD 目前（應該）顯示的表情，開機後韌體預設 idle
    lcd_text: str = ""                      # LCD 目前（應該）顯示的台詞，還沒送過任何話就是空字串
    lcd_updated_ts: Optional[datetime] = None  # 上面兩個欄位最後一次成功送出的時間
    idle: bool = False                     # 很久沒有鍵盤滑鼠活動
    paused: bool = False                   # 使用者暫停記錄

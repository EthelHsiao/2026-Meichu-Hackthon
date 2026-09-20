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
    last_telemetry: Optional[dict] = None  # 最近一筆原始 FSR/IMU 數值，只給 dashboard 即時顯示
    idle: bool = False                     # 很久沒有鍵盤滑鼠活動
    paused: bool = False                   # 使用者暫停記錄

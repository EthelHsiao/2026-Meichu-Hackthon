"""ESP32 <-> AIPC 的訊息格式（一則一個 JSON），走 WebSocket（見 docs/api.html §①）。
2026-09-20：原本規劃 USB Serial 換行框架，改成 WebSocket text frame 傳送同樣的
JSON（ESP32 端這兩種格式從沒實作過 serial 版本，直接定案成 WebSocket，
Serial 規劃退役）。訊息本身的 dataclass/欄位不變，只是傳輸層換了。"""
import json
from dataclasses import dataclass
from typing import Literal, Optional, Union

EXPRESSIONS = ("neutral", "happy", "joy", "love", "sad", "sleepy", "surprised", "thinking", "worried")
Expr = Literal["neutral", "happy", "joy", "love", "sad", "sleepy", "surprised", "thinking", "worried"]
# double_tap：壓 FSR1 兩下，觸發「拍照分析作業」流程（見 docs/api.html §⑥）。
# 在 ESP32 韌體本地判斷、只送離散事件，不用 AIPC 從連續數值重新判斷。
TouchKind = Literal["squeeze", "pat", "shake", "lift", "putdown", "double_tap"]
MAX_TEXT_CHARS = 40  # 1.8" LCD 放得下的量，實測後再調


# ---------------- ESP32 -> AIPC ----------------
@dataclass
class TouchEvent:
    """{"t":"touch","kind":"squeeze","strength":0.8,"dur_ms":1200}"""
    kind: TouchKind
    strength: float = 0.0  # 0~1
    dur_ms: int = 0


@dataclass
class Heartbeat:
    """{"t":"hb","uptime_s":321}"""
    uptime_s: int


@dataclass
class TelemetrySample:
    """{"schema_version":1,"type":"telemetry","seq":...,"fsr":{...},"imu":{...}}
    原始感測器數值（見 esp32-bringup/tools/receive_telemetry.py 的 validate_sample），
    只給 dashboard 即時顯示用，不寫進記憶庫，跟 touch/hb 用不同欄位（"type" 不是
    "t"）分辨，所以要在 parse_line 裡先於 t 判斷。"""
    seq: int
    fsr: dict
    imu: dict


def parse_line(line: str) -> Optional[Union[TouchEvent, Heartbeat, TelemetrySample]]:
    """ESP32 也會印 debug 文字，不是 JSON 或不認得的行一律回 None。"""
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return None
    if msg.get("type") == "telemetry":
        return TelemetrySample(seq=msg.get("seq", 0), fsr=msg.get("fsr") or {}, imu=msg.get("imu") or {})
    t = msg.pop("t", None)
    if t == "touch":
        return TouchEvent(**msg)
    if t == "hb":
        return Heartbeat(**msg)
    return None


# ---------------- AIPC -> ESP32 ----------------
@dataclass
class SayCommand:
    """{"t":"say","expr":"thinking","text":"..."}"""
    expr: Expr
    text: str

    def to_line(self) -> str:
        return json.dumps({"t": "say", "expr": self.expr, "text": self.text[:MAX_TEXT_CHARS]}, ensure_ascii=False) + "\n"


@dataclass
class ExprCommand:
    """{"t":"expr","expr":"sleepy"}：只換表情、不說話"""
    expr: Expr

    def to_line(self) -> str:
        return json.dumps({"t": "expr", "expr": self.expr}) + "\n"


@dataclass
class BuzzCommand:
    """{"t":"buzz","pattern":"chirp"}：驅動被動蜂鳴器做簡單音效回饋。
    pattern 由韌體端定義具體音效（例如 "chirp"、"confirm"），這裡不限制字面值，
    韌體不認得的 pattern 應該安靜忽略，不要讓 AIPC 因為打錯字就整個斷線。"""
    pattern: str

    def to_line(self) -> str:
        return json.dumps({"t": "buzz", "pattern": self.pattern}) + "\n"

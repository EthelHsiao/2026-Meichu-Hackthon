"""ESP32 <-> AIPC 的 USB 序列訊息（一行一個 JSON）。格式說明見 docs/data_structures.md。"""
import json
from dataclasses import dataclass
from typing import Literal, Optional, Union

EXPRESSIONS = ("neutral", "happy", "joy", "love", "sad", "sleepy", "surprised", "thinking", "worried")
Expr = Literal["neutral", "happy", "joy", "love", "sad", "sleepy", "surprised", "thinking", "worried"]
TouchKind = Literal["squeeze", "pat", "shake", "lift", "putdown"]
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


def parse_line(line: str) -> Optional[Union[TouchEvent, Heartbeat]]:
    """ESP32 也會印 debug 文字，不是 JSON 或不認得的行一律回 None。"""
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return None
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

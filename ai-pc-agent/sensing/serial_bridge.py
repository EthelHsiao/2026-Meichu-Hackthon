"""ESP32 <-> AIPC 的 USB 序列橋。訊息格式見 ../protocol.py。"""


class SerialBridge:
    def __init__(self, port: str, baud: int):
        raise NotImplementedError

    def read_event(self):
        """讀一行、用 protocol.parse_line 解析；非 JSON 的 debug 行略過。"""
        raise NotImplementedError

    def send(self, cmd):
        """cmd 是 SayCommand 或 ExprCommand。"""
        raise NotImplementedError

"""截圖 -> 一句話描述（含錯誤類型）。
⚠ VLM 跑在 AIPC 還是 MI300 尚未決定，介面先固定，實作之後再接。"""


def describe(image, app: str, window_title: str) -> dict:
    """回傳 {"text": "...", "error": "KeyError: 'response'" 或 None}"""
    raise NotImplementedError

"""呼叫 MI300（OpenAI 相容 API）。"""


def reply(messages: list[dict]) -> dict:
    """回傳 {"expr": ..., "text": ...}；MI300 連不上時回 fallback 句子。"""
    raise NotImplementedError

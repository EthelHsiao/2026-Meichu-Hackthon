"""組要送給 MI300 的 prompt。"""


def build_messages(state, recent: list[str], related: list[str], user_text: str = "") -> list[dict]:
    """回傳 OpenAI 格式 messages：
    system：桌寵人設 + 只能回 {"expr": EXPRESSIONS 之一, "text": 不超過 MAX_TEXT_CHARS 字}
    user  ：【現在】【觸覺】【最近狀態】【相關記憶】【使用者說】
    user_text 為空代表是主動發話（例如卡太久）。"""
    raise NotImplementedError

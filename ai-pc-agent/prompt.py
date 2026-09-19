"""組要送給 MI300 的 prompt。"""

from protocol import EXPRESSIONS, MAX_TEXT_CHARS

SYSTEM_PROMPT = (
    "你是桌上的毛茸茸桌寵，安靜、簡短、不說教，會根據使用者的工作情境保持記憶、"
    "有 context 地回覆。只回傳一個 JSON 物件，不要有其他文字或 markdown："
    '{"expr": 表情, "text": 回覆文字}。\n'
    f"expr 只能是以下其中之一：{', '.join(EXPRESSIONS)}。\n"
    f"text 不超過 {MAX_TEXT_CHARS} 個字，語氣自然、不長篇大論、不重複使用者的話。"
)


def _facts_block(facts: list[str]) -> str:
    return "\n".join(f"- {fact}" for fact in facts) if facts else "（尚無已知事實）"


def _lines_block(lines: list[str]) -> str:
    return "\n".join(f"- {line}" for line in lines) if lines else "（無）"


def build_messages(
    state,
    recent: list[str],
    related: list[str],
    user_text: str = "",
    *,
    facts: list[str] | None = None,
    touch: dict | None = None,
) -> list[dict]:
    """回傳 OpenAI 格式 messages：
    system：桌寵人設 + 只能回 {"expr": EXPRESSIONS 之一, "text": 不超過 MAX_TEXT_CHARS 字}
    user  ：【使用者檔案】【最近狀態】【相關記憶】【觸覺】【使用者說】
    user_text 為空代表是主動發話（例如同一件事做太久），此時 MI300 要自己決定
    要不要開口、開口要說什麼；state 是 state.py 的 ContextState（或相容的 dict）。
    """
    app = getattr(state, "app", None) or (state.get("app") if isinstance(state, dict) else None) or "（不明）"
    activity = getattr(state, "activity", None) or (state.get("activity") if isinstance(state, dict) else None) or "（不明）"
    error = getattr(state, "error", None) or (state.get("error") if isinstance(state, dict) else None)

    now_block = f"app：{app}\n活動：{activity}" + (f"\n錯誤：{error}" if error else "")
    touch_block = f"{touch.get('kind')}（強度 {touch.get('strength', 0):.1f}）" if touch else "（無）"

    user_content = (
        f"【使用者檔案】\n{_facts_block(facts or [])}\n\n"
        f"【現在】\n{now_block}\n\n"
        f"【最近狀態】\n{_lines_block(recent)}\n\n"
        f"【相關記憶】\n{_lines_block(related)}\n\n"
        f"【觸覺】{touch_block}\n\n"
        f"【使用者說】{user_text or '（沒有，這是主動發話）'}"
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

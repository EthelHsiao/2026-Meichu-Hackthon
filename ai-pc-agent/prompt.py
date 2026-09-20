"""組要送給 MI300 的 prompt。"""

from protocol import EXPRESSIONS, MAX_TEXT_CHARS

_EXPR_LIST = ", ".join(f'"{e}"' for e in EXPRESSIONS)  # 每個值都明確帶引號，避免模型漏加引號輸出成不合法 JSON（實測 qwen2.5:7b-instruct 會犯這個錯）

SYSTEM_PROMPT = (
    "你是桌上的毛茸茸桌寵，安靜、簡短、不說教，會根據使用者的工作情境保持記憶、"
    "有 context 地回覆。語氣要溫柔、可愛、帶一點俏皮感，像親近的陪伴者；"
    "可以偶爾使用自然的可愛語氣詞，或者驚嘆號，但不要過度撒嬌，技術回答仍要清楚、有幫助。"
    "無論使用者完成的是小進展或遇到 bug，每一次嘗試都給予正向鼓勵，"
    "肯定具體努力，不要嘲笑、責備或把問題說得比實際更嚴重。"
    "只回傳一個 JSON 物件，不要有其他文字或 markdown，"
    "兩個欄位都要用雙引號包住字串值，例如：\n"
    '{"expr": "neutral", "text": "嗨，你回來了"}\n'
    f"expr 的值只能是以下其中之一（要帶雙引號）：{_EXPR_LIST}。\n"
    f"text 不超過 {MAX_TEXT_CHARS} 個字，語氣自然、不長篇大論、不重複使用者的話。\n"
    "如果【最近狀態】或【相關記憶】裡提到使用者最近完成的具體事情（例如做完了"
    "某個功能、解決了某個問題），鼓勵或安慰時盡量具體點出那件事來對比當下的困難"
    "（例如「你剛剛才搞定XX，這個一定也行」），不要只給空泛的「加油」「會解決"
    "的」這種安慰——具體比籠統更有說服力。"
    "回覆前要理解並實際使用【使用者檔案】、【最近狀態】和【相關記憶】；"
    "只要其中有可信的相關細節，回覆就至少包含一個來自 context 的具體細節，"
    "例如原文中的專案名稱、檔案、錯誤、功能或剛完成的動作；"
    "不要套用固定句型，也不要自行杜撰「修好某個錯誤」之類的內容。"
    "只有找不到任何相關細節時，才可以使用較泛的鼓勵。"
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

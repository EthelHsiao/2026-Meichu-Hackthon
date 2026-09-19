"""記憶壓縮（≈ OpenClaw 的 dreaming：先用規則篩，再讓模型整理）。

分工：
- 程式規則決定「哪些可以壓縮」：整個時段都結束超過 COMPACT_AFTER_HOURS 的 raw
- LLM 只負責「寫摘要」（summarize 由呼叫端傳進來，用 AIPC 還是 MI300 的模型之後再決定）
- 刪除由程式執行，而且只在摘要成功寫入之後；摘要失敗就保留原始記錄，下次再試
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable, Optional

import config
from memory.store import Memory, MemoryStore, now_iso

# 輸入：該時段的記錄（已格式化成「[09:20–10:00] 在 main.py 遇到 KeyError」），輸出：一段摘要
Summarizer = Callable[[list[str]], str]


def split_sessions(memories: list[Memory], gap_min: int = config.SESSION_GAP_MIN) -> list[list[Memory]]:
    """依時間排序後，前一筆結束到下一筆開始中斷超過 gap_min 分鐘就切一段。"""
    sessions: list[list[Memory]] = []
    gap = timedelta(minutes=gap_min)
    for mem in sorted(memories, key=lambda m: m.ts_start):
        if sessions and datetime.fromisoformat(mem.ts_start) - datetime.fromisoformat(sessions[-1][-1].ts_end) <= gap:
            sessions[-1].append(mem)
        else:
            sessions.append([mem])
    return sessions


def run_compaction(store: MemoryStore, summarize: Summarizer, *, now: Optional[datetime] = None) -> int:
    """回傳這次壓縮了幾個時段。"""
    now = now or datetime.now().astimezone()
    cutoff = now - timedelta(hours=config.COMPACT_AFTER_HOURS)
    raws = store.db.execute(
        "SELECT id, ts_start, ts_end, level, source, app, text, error_sig, importance "
        "FROM memories WHERE level='raw' ORDER BY ts_start"
    ).fetchall()
    sessions = split_sessions([Memory(*r) for r in raws])

    done = 0
    for session in sessions:
        # 最後一段可能還在進行中；整段都結束夠久才壓縮
        if datetime.fromisoformat(max(m.ts_end for m in session)) > cutoff:
            continue
        try:
            summary = summarize([m.line() for m in session]).strip()
        except Exception as exc:  # noqa: BLE001 — 摘要失敗就保留 raw，下次再試
            print(f"[compaction] 摘要失敗，保留原始記錄: {exc}")
            continue
        if not summary:
            continue

        errors = {m.error_sig for m in session if m.error_sig}
        # 新增摘要跟刪除原始記錄放在同一個 transaction，中途當掉不會留下重複
        store._insert(
            commit=False,
            ts_start=min(m.ts_start for m in session),
            ts_end=max(m.ts_end for m in session),
            level="summary",
            source="summary",
            app=None,
            state_key=None,
            text=summary,
            error_sig=",".join(sorted(errors)) or None,
            importance=config.IMPORTANCE["summary"] + (config.ERROR_IMPORTANCE_BONUS if errors else 0.0),
        )
        ids = [m.id for m in session]
        store.db.execute(f"DELETE FROM memories WHERE id IN ({','.join('?' * len(ids))})", ids)
        store.db.commit()
        done += 1

    store.set_setting("last_compaction", now_iso())
    return done

"""記憶模組測試。用假的 embedder（字元 hash），不用下載 bge-m3 就能跑：
    cd ai-pc-agent && python -m pytest tests
"""
from datetime import datetime, timedelta

import numpy as np
import pytest

from memory.compaction import run_compaction, split_sessions
from memory.retrieve import _fts_query, search
from memory.store import MemoryStore

T0 = datetime(2026, 9, 19, 9, 0).astimezone()


def at(minutes: float) -> str:
    return (T0 + timedelta(minutes=minutes)).isoformat(timespec="seconds")


class FakeEmbedder:
    """字元 bag-of-hash：有共同字元的句子向量就比較接近，夠用來測排序邏輯。"""
    name = "fake"

    def encode(self, texts):
        out = np.zeros((len(texts), 64), dtype=np.float32)
        for i, t in enumerate(texts):
            for ch in t:
                out[i, hash(ch) % 64] += 1
            out[i] /= np.linalg.norm(out[i]) or 1
        return out


@pytest.fixture
def store():
    return MemoryStore(":memory:", FakeEmbedder())


def test_same_state_extends_instead_of_insert(store):
    a = store.add_or_extend("screen", "在 main.py 遇到 KeyError", state_key="code|main.py|KeyError", ts=at(0))
    b = store.add_or_extend("screen", "在 main.py 遇到 KeyError", state_key="code|main.py|KeyError", ts=at(20))
    assert a == b
    [m] = store.recent(10)
    assert (m.ts_start, m.ts_end) == (at(0), at(20))


def test_new_row_when_state_changes_or_gap_too_long(store):
    store.add_or_extend("screen", "寫 main.py", state_key="k1", ts=at(0))
    store.add_or_extend("screen", "看 YouTube", state_key="k2", ts=at(5))
    store.add_or_extend("screen", "看 YouTube", state_key="k2", ts=at(5 + 120))  # 中斷 2 小時
    assert len(store.recent(10)) == 3


def test_utterances_never_merge(store):
    store.add_or_extend("speech", "這個怎麼修", ts=at(0))
    store.add_or_extend("speech", "這個怎麼修", ts=at(1))
    assert len(store.recent(10)) == 2


def test_error_and_speech_get_higher_importance(store):
    store.add_or_extend("screen", "寫 code", state_key="a", ts=at(0))
    store.add_or_extend("screen", "KeyError", state_key="b", error_sig="KeyError", ts=at(1))
    store.add_or_extend("speech", "好累", ts=at(2))
    screen, err, speech = store.recent(10)
    assert screen.importance < err.importance and screen.importance < speech.importance


def test_fts_query_keeps_only_code_like_terms():
    assert _fts_query("剛剛那個 KeyError 在 main.py 怎麼修") == '"KeyError" OR "main.py"'
    assert _fts_query("你好") == ""


def test_bm25_finds_exact_error_string(store):
    store.add_or_extend("screen", "在瀏覽器看新聞", state_key="a", ts=at(0))
    store.add_or_extend("screen", "main.py 出現 KeyError: 'response'", state_key="b", error_sig="KeyError", ts=at(1))
    store.add_or_extend("screen", "在寫 ESP32 LCD 程式", state_key="c", ts=at(2))
    hits = search(store, "KeyError 怎麼辦", k=3, now=T0 + timedelta(minutes=3))
    assert "KeyError" in hits[0].memory.text
    assert hits[0].text == 1.0


def test_old_memories_decay(store):
    store.add_or_extend("screen", "debug KeyError", state_key="a", ts=at(0))
    store.add_or_extend("screen", "debug KeyError", state_key="b", ts=at(60 * 24 * 6))  # 6 天後同一件事
    hits = search(store, "KeyError", k=2, now=T0 + timedelta(days=6))
    assert hits[0].memory.ts_start == at(60 * 24 * 6)
    assert hits[1].decay == pytest.approx(0.25, rel=0.01)  # raw 半衰期 3 天 → 6 天剩 1/4


def test_exclude_ids(store):
    a = store.add_or_extend("screen", "debug KeyError", state_key="a", ts=at(0))
    hits = search(store, "KeyError", exclude_ids=[a], now=T0)
    assert hits == []


def test_split_sessions_by_gap(store):
    for m, key in [(0, "a"), (10, "b"), (20, "c"), (120, "d"), (130, "e")]:
        store.add_or_extend("screen", key * 3, state_key=key, ts=at(m))
    sessions = split_sessions(store.recent(10))
    assert [len(s) for s in sessions] == [3, 2]


def test_compaction_replaces_old_raw_with_summary(store):
    store.add_or_extend("screen", "寫 API", state_key="a", ts=at(0))
    store.add_or_extend("screen", "遇到 KeyError", state_key="b", error_sig="KeyError", ts=at(20))
    store.add_or_extend("screen", "最近的事", state_key="c", ts=at(60 * 30))  # 還沒超過 24 小時

    seen = []
    def summarize(lines):
        seen.append(lines)
        return "09:00–09:20 開發 API，卡在 KeyError"

    n = run_compaction(store, summarize, now=T0 + timedelta(hours=31))
    assert n == 1
    assert len(seen[0]) == 2
    levels = [(m.level, m.text) for m in store.recent(10)]
    assert levels == [("summary", "09:00–09:20 開發 API，卡在 KeyError"), ("raw", "最近的事")]
    [summary] = [m for m in store.recent(10) if m.level == "summary"]
    assert summary.error_sig == "KeyError"
    # 摘要也要搜得到
    assert search(store, "KeyError", now=T0 + timedelta(hours=31))[0].memory.level == "summary"


def test_compaction_keeps_raw_when_summarizer_fails(store):
    store.add_or_extend("screen", "寫 API", state_key="a", ts=at(0))
    def boom(lines):
        raise RuntimeError("MI300 斷線")
    assert run_compaction(store, boom, now=T0 + timedelta(days=2)) == 0
    assert [m.level for m in store.recent(10)] == ["raw"]


def test_delete_range_and_fts_stays_in_sync(store):
    store.add_or_extend("screen", "看到 password 畫面", state_key="a", ts=at(0))
    store.add_or_extend("screen", "寫 main.py", state_key="b", ts=at(30))
    assert store.delete_range(at(-1), at(1)) == 1
    hits = search(store, "password", now=T0)
    assert all("password" not in h.memory.text and h.text == 0 for h in hits)


def test_profile_facts(store):
    store.add_fact("在做 ESP32 桌寵專案")
    store.add_fact("在做 ESP32 桌寵專案")  # 重複不會多一筆
    store.add_fact("晚上比較常寫 code", source="extracted")
    assert store.facts() == ["在做 ESP32 桌寵專案", "晚上比較常寫 code"]
    store.remove_fact("晚上比較常寫 code")
    assert store.facts() == ["在做 ESP32 桌寵專案"]


def test_reembed_after_model_change(store):
    store.add_or_extend("screen", "寫 main.py", state_key="a", ts=at(0))
    class Other(FakeEmbedder):
        name = "other"
    store.embedder = Other()
    assert len(store.all_vectors()[0]) == 0  # 舊模型的向量不拿來比
    assert store.reembed_stale() == 1
    assert len(store.all_vectors()[0]) == 1


def test_line_shows_duration(store):
    for i in range(0, 95 * 3 + 1):  # 每 20 秒截一次，看了 95 分鐘
        store.add_or_extend("screen", "看 YouTube", state_key="yt", ts=at(i / 3))
    store.add_or_extend("speech", "好無聊", ts=at(96))
    long, short = store.recent(10)
    assert long.line().endswith("09:00–10:35，1 小時 35 分鐘] 看 YouTube")
    assert short.line().endswith("10:36] 好無聊")

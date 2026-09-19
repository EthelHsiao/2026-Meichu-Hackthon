"""RAG 檢索：hybrid search（向量 + BM25），做法參考 OpenClaw。

最後分數 = (W_VECTOR × cosine + W_TEXT × BM25分數) × 時間衰減 × importance
- cosine：問題向量跟所有記憶向量做內積（numpy 暴力搜尋，幾千筆不到 1ms）
- BM25：SQLite FTS5 內建，負責 KeyError、檔名這類精確字串
- 時間衰減：0.5 ^ (經過天數 / 半衰期)，raw 衰減快、summary 衰減慢
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

import numpy as np

import config
from memory.store import Memory, MemoryStore


@dataclass
class Hit:
    memory: Memory
    score: float
    vector: float  # 除錯用：各項分數拆開看
    text: float
    decay: float


def search(
    store: MemoryStore,
    query: str,
    k: int = config.RAG_TOP_K,
    *,
    exclude_ids: Iterable[int] = (),
    now: Optional[datetime] = None,
) -> list[Hit]:
    """回傳分數最高的 k 筆。exclude_ids 用來排除已經放在【最近狀態】裡的記錄，避免 prompt 重複。"""
    now = now or datetime.now().astimezone()
    exclude = set(exclude_ids)
    n = config.RAG_CANDIDATES

    # ---- 向量 ----
    vec_scores: dict[int, float] = {}
    ids, mat = store.all_vectors()
    if len(ids):
        q = store.embedder.encode([query])[0]
        sims = mat @ q
        for i in np.argsort(-sims)[:n]:
            vec_scores[int(ids[i])] = max(float(sims[i]), 0.0)  # 負的 cosine 當 0

    # ---- BM25 ----
    text_scores = _bm25(store, query, n)

    # ---- 合併 ----
    candidates = (vec_scores.keys() | text_scores.keys()) - exclude
    memories = store.get(list(candidates))
    hits = []
    for mid, mem in memories.items():
        v = vec_scores.get(mid, 0.0)
        t = text_scores.get(mid, 0.0)
        d = _decay(mem, now)
        score = (config.W_VECTOR * v + config.W_TEXT * t) * d * mem.importance
        hits.append(Hit(mem, score, v, t, d))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:k]


def _bm25(store: MemoryStore, query: str, n: int) -> dict[int, float]:
    """FTS5 的 bm25() 越小越相關；依名次轉成 0~1 分數：第 1 名 1.0、第 2 名 0.5、第 3 名 0.33…"""
    match = _fts_query(query)
    if not match:
        return {}
    rows = store.db.execute(
        "SELECT rowid FROM memories_fts WHERE memories_fts MATCH ? ORDER BY bm25(memories_fts) LIMIT ?",
        (match, n),
    ).fetchall()
    return {r[0]: 1.0 / (rank + 1) for rank, r in enumerate(rows)}


def _fts_query(query: str) -> str:
    """只拿問題裡的英數字詞（KeyError、main.py、ESP32…）用 OR 串起來。
    中文不進 BM25：問句沒有空白可切，硬切成 3 字一組會撈到一堆「那個錯」這種雜訊，
    中文語意交給向量搜尋。trigram 比對不到少於 3 個字的詞，也直接丟掉。"""
    terms = [t.strip(".:'-") for t in re.findall(r"[A-Za-z0-9_.:'\-]+", query)]
    terms = dict.fromkeys(t for t in terms if len(t) >= 3)  # 去重、保留順序
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)


def _decay(mem: Memory, now: datetime) -> float:
    half_life = config.HALF_LIFE_DAYS.get(mem.level)
    if not half_life:
        return 1.0
    age_days = max((now - datetime.fromisoformat(mem.ts_end)).total_seconds() / 86400, 0.0)
    return 0.5 ** (age_days / half_life)

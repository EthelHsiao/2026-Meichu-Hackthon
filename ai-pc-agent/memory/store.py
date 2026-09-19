"""記憶資料庫的讀寫。schema 見 schema.sql，設計見 docs/data_structures.md 第 ③ 節。"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

import config

SCHEMA = Path(__file__).with_name("schema.sql")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Memory:
    id: int
    ts_start: str
    ts_end: str
    level: str
    source: str
    app: Optional[str]
    text: str
    error_sig: Optional[str]
    importance: float

    def line(self) -> str:
        """放進 prompt 的格式：[09:20–10:00，40 分鐘] 在 main.py 遇到 KeyError
        分鐘數直接寫出來，不讓 LLM 自己從時間範圍算減法（容易算錯）。"""
        start = datetime.fromisoformat(self.ts_start)
        end = datetime.fromisoformat(self.ts_end)
        day = "" if start.date() == datetime.now().astimezone().date() else start.strftime("%m/%d ")
        minutes = int((end - start).total_seconds() // 60)
        if minutes < 1:
            span = start.strftime("%H:%M")
        else:
            dur = f"{minutes} 分鐘" if minutes < 60 else f"{minutes // 60} 小時 {minutes % 60} 分鐘"
            span = f"{start:%H:%M}–{end:%H:%M}，{dur}"
        return f"[{day}{span}] {self.text}"


_MEMORY_COLS = "id, ts_start, ts_end, level, source, app, text, error_sig, importance"


class MemoryStore:
    def __init__(self, path: str, embedder):
        """embedder 需要有 .name 跟 .encode(list[str]) -> (n, dim) float32（見 embedder.py）。"""
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.executescript(SCHEMA.read_text(encoding="utf-8"))
        self.embedder = embedder

    # ------------------------------------------------------------------
    # 寫入
    # ------------------------------------------------------------------
    def add_or_extend(
        self,
        source: str,
        text: str,
        *,
        app: str = "",
        state_key: str = "",
        error_sig: str = "",
        ts: Optional[str] = None,
    ) -> int:
        """跟同 source 的上一筆 state_key 相同、且中斷沒超過 SESSION_GAP_MIN，就只延長 ts_end；
        否則新增一筆並算 embedding。回傳記錄 id。
        state_key 為空（例如使用者說的話）一律新增。"""
        ts = ts or now_iso()
        if state_key:
            last = self.db.execute(
                "SELECT id, state_key, ts_end FROM memories WHERE level='raw' AND source=? "
                "ORDER BY ts_end DESC LIMIT 1",
                (source,),
            ).fetchone()
            if last and last[1] == state_key:
                gap = datetime.fromisoformat(ts) - datetime.fromisoformat(last[2])
                if gap <= timedelta(minutes=config.SESSION_GAP_MIN):
                    self.db.execute("UPDATE memories SET ts_end=? WHERE id=?", (ts, last[0]))
                    self.db.commit()
                    return last[0]

        importance = config.IMPORTANCE.get(source, 1.0) + (config.ERROR_IMPORTANCE_BONUS if error_sig else 0.0)
        return self._insert(
            ts_start=ts, ts_end=ts, level="raw", source=source, app=app or None,
            state_key=state_key or None, text=text, error_sig=error_sig or None, importance=importance,
        )

    def _insert(self, *, commit: bool = True, **row) -> int:
        vec = self.embedder.encode([row["text"]])[0]
        row.update(embedding=vec.astype(np.float32).tobytes(), embed_model=self.embedder.name)
        cols = ", ".join(row)
        marks = ", ".join("?" * len(row))
        cur = self.db.execute(f"INSERT INTO memories ({cols}) VALUES ({marks})", tuple(row.values()))
        if commit:
            self.db.commit()
        return cur.lastrowid

    def reembed_stale(self) -> int:
        """換 embedding 模型後，把不是用目前模型算的向量全部重算。回傳重算筆數。"""
        rows = self.db.execute(
            "SELECT id, text FROM memories WHERE embed_model IS NOT ? OR embedding IS NULL",
            (self.embedder.name,),
        ).fetchall()
        if not rows:
            return 0
        vecs = self.embedder.encode([t for _, t in rows])
        self.db.executemany(
            "UPDATE memories SET embedding=?, embed_model=? WHERE id=?",
            [(v.astype(np.float32).tobytes(), self.embedder.name, i) for (i, _), v in zip(rows, vecs)],
        )
        self.db.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # 讀取
    # ------------------------------------------------------------------
    def recent(self, n: int) -> list[Memory]:
        """最新 n 筆（依 ts_end），時間由舊到新排列，給 prompt 的【最近狀態】。"""
        rows = self.db.execute(
            f"SELECT {_MEMORY_COLS} FROM memories ORDER BY ts_end DESC LIMIT ?", (n,)
        ).fetchall()
        return [Memory(*r) for r in reversed(rows)]

    def get(self, ids: list[int]) -> dict[int, Memory]:
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self.db.execute(f"SELECT {_MEMORY_COLS} FROM memories WHERE id IN ({marks})", ids).fetchall()
        return {r[0]: Memory(*r) for r in rows}

    def all_vectors(self) -> tuple[np.ndarray, np.ndarray]:
        """(ids, 矩陣)。只取目前模型算的向量，其他模型的向量不能拿來比。"""
        rows = self.db.execute(
            "SELECT id, embedding FROM memories WHERE embed_model=? AND embedding IS NOT NULL",
            (self.embedder.name,),
        ).fetchall()
        if not rows:
            return np.empty(0, dtype=np.int64), np.empty((0, 0), dtype=np.float32)
        ids = np.array([r[0] for r in rows], dtype=np.int64)
        mat = np.stack([np.frombuffer(r[1], dtype=np.float32) for r in rows])
        return ids, mat

    # ------------------------------------------------------------------
    # 清除（使用者手動）
    # ------------------------------------------------------------------
    def delete_range(self, ts_from: str, ts_to: str) -> int:
        """刪掉跟 [ts_from, ts_to] 有重疊的記憶，例如「刪掉最近 1 小時」。回傳刪除筆數。"""
        cur = self.db.execute("DELETE FROM memories WHERE ts_end >= ? AND ts_start <= ?", (ts_from, ts_to))
        self.db.commit()
        return cur.rowcount

    def clear_all(self) -> None:
        self.db.execute("DELETE FROM memories")
        self.db.execute("DELETE FROM profile")
        self.db.commit()

    # ------------------------------------------------------------------
    # 使用者檔案（≈ OpenClaw 的 USER.md）
    # ------------------------------------------------------------------
    def add_fact(self, fact: str, source: str = "user") -> None:
        ts = now_iso()
        self.db.execute(
            "INSERT INTO profile (fact, source, created_at, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(fact) DO UPDATE SET updated_at=excluded.updated_at",
            (fact, source, ts, ts),
        )
        self.db.commit()

    def remove_fact(self, fact: str) -> None:
        self.db.execute("DELETE FROM profile WHERE fact=?", (fact,))
        self.db.commit()

    def facts(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT fact FROM profile ORDER BY created_at")]

    # ------------------------------------------------------------------
    # settings
    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.db.commit()

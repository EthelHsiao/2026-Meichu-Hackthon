"""debug_api.py 的除錯/測試 endpoint 測試。用假 embedder + 記憶體資料庫，
不會碰到真正的 data/memory.db，也不需要下載 bge-m3。
"""
import pytest
from fastapi.testclient import TestClient

import config
import debug_api
import main
from memory.store import MemoryStore
from tests.test_memory import FakeEmbedder


@pytest.fixture
def client():
    debug_api.companion.memory = MemoryStore(":memory:", FakeEmbedder())
    with TestClient(debug_api.app) as c:
        yield c


def test_gesture_updates_status_and_writes_touch_memory(client):
    resp = client.post("/debug/gesture", json={"kind": "squeeze", "strength": 0.5, "dur_ms": 100})
    assert resp.status_code == 200

    status = client.get("/debug/status").json()
    assert status["last_touch"] == {"kind": "squeeze", "strength": 0.5}

    recent = client.get("/debug/memory/recent").json()
    assert any(m["source"] == "touch" for m in recent)


def test_double_tap_opens_countdown_page(client, monkeypatch):
    launched = []
    monkeypatch.setattr(main.subprocess, "Popen", lambda args, **kw: launched.append(args))
    resp = client.post("/debug/gesture", json={"kind": "double_tap", "strength": 1.0, "dur_ms": 200})
    assert resp.status_code == 200
    assert launched == [["firefox", "--new-tab", config.HOMEWORK_COUNTDOWN_URL]]


def test_memory_seed_then_clear(client):
    seeded = client.post("/debug/memory/seed").json()
    assert seeded["ok"] is True
    assert len(seeded["inserted"]) == len(debug_api.SEED_MEMORIES)

    recent = client.get("/debug/memory/recent?n=50").json()
    assert len(recent) == len(debug_api.SEED_MEMORIES)

    client.delete("/debug/memory/clear")
    assert client.get("/debug/memory/recent").json() == []


def test_memory_seed_accepts_custom_scenario(client):
    custom = {
        "entries": [
            {"source": "screen", "text": "前端頁面完成了", "hours_ago": 2},
            {"source": "speech", "text": "好煩喔我超爛", "hours_ago": 0},
        ]
    }
    seeded = client.post("/debug/memory/seed", json=custom).json()
    assert seeded["ok"] is True
    assert len(seeded["inserted"]) == 2

    recent = client.get("/debug/memory/recent?n=50").json()
    assert len(recent) == 2
    assert not any(m["source"] == "homework" for m in recent)  # 沒有混進預設那批


def test_retrieve_ranks_keyword_match_above_unrelated_memory(client):
    client.post("/debug/memory/seed")
    hits = client.get("/debug/retrieve", params={"query": "KeyError"}).json()
    assert hits, "應該至少找到一筆"
    # 種子資料裡明確提到 KeyError 的那幾筆分數應該排在只提到 YouTube 的那筆前面
    top_texts = [h["memory_text"] for h in hits]
    assert any("KeyError" in t for t in top_texts[:3])
    for h in hits:
        assert set(h) == {
            "id", "memory_text", "source", "ts_end", "score",
            "vector_score", "text_score", "decay", "importance",
        }


if __name__ == "__main__":
    pytest.main([__file__, "-q"])

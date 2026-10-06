"""debug_api.py 的除錯/測試 endpoint 測試。用假 embedder + 記憶體資料庫，
不會碰到真正的 data/memory.db，也不需要下載 bge-m3。
"""
import pytest
from fastapi.testclient import TestClient

import config
import debug_api
import main
from memory.store import MemoryStore
from protocol import TelemetrySample
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


def test_esp32_send_reports_failure_when_not_connected(client):
    # 測試環境沒有真的 ESP32 連線，companion.esp32._ws 是 None——這支 endpoint
    # 該回 ok:false + 錯誤原因，不是拋例外變成 500。
    resp = client.post("/debug/esp32/send", json={"t": "say", "expr": "happy", "text": "hi"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert "error" in body


def test_esp32_send_rejects_unknown_command_type(client):
    resp = client.post("/debug/esp32/send", json={"t": "dance"})
    assert resp.json() == {"ok": False, "error": "t 必須是 say / expr / buzz 其中之一"}


def test_status_reports_last_telemetry_field(client):
    status = client.get("/debug/status").json()
    assert "last_telemetry" in status
    assert status["last_telemetry"] is None  # 還沒收過任何一筆


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


def test_both_dashboard_panels_read_the_same_telemetry(client):
    # 合併 main（ESP32 WebSocket 測試面板讀 /debug/status 的 last_telemetry）跟
    # feat/companion-hotspot-mdns（即時感測器面板讀 /debug/telemetry）：兩邊現在共用
    # state.last_telemetry 這一份資料，而且 device_id / boot_id 都帶得出來。
    debug_api.companion.state.last_telemetry = None
    assert client.get("/debug/telemetry").json() is None
    debug_api.companion._on_esp32_telemetry(TelemetrySample(
        seq=7, fsr={"enabled": True, "raw": [1, 2]}, imu={"ok": False, "status": "x"},
        device_id="dev-1", boot_id="boot-1",
    ))
    from_endpoint = client.get("/debug/telemetry").json()
    assert client.get("/debug/status").json()["last_telemetry"] == from_endpoint
    assert (from_endpoint["device_id"], from_endpoint["boot_id"], from_endpoint["seq"]) == ("dev-1", "boot-1", 7)
    debug_api.companion.state.last_telemetry = None


def test_status_keeps_fields_from_both_sides(client):
    status = client.get("/debug/status").json()
    for key in (
        "last_telemetry",                                   # main
        "last_touch_ts", "stt_connected", "last_mic_ts", "mic_frames_total",   # feat/companion-hotspot-mdns
        "lcd_expr", "lcd_text", "lcd_updated_ts", "cam_reachable",
    ):
        assert key in status, key


def test_both_manual_trigger_endpoints_exist(client):
    # main 的 /debug/esp32/send（say/expr/buzz）跟分支的 /debug/expr（直接換表情）都要在。
    assert client.post("/debug/expr", json={"expr": "happy"}).json() == {"ok": True, "expr": "happy"}
    assert client.post("/debug/esp32/send", json={"t": "expr", "expr": "happy"}).json()["ok"] is False  # 沒連線


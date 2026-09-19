"""AIPC 本機測試/除錯 API（見 docs/api.html §⑧、計畫第 9 節）。

目的：驗證整個流程不需要真的按實體 FSR、對麥克風講話、或等 20~36 秒的截圖排程——
可以直接 curl（例如透過 SSH）觸發每一步，配合 GET /debug/status、
GET /debug/memory/recent 檢查結果有沒有正確發生。只給本機/內網用，預設監聽
127.0.0.1，不要對外開放（沒有任何驗證機制）。

用法：
    uvicorn debug_api:app --host 127.0.0.1 --port 8090
這支模組會自己建立、常駐一個 main.Companion 實例（背景跑 esp32/reply/compaction
迴圈），下面的 endpoint 都是操作同一個實例，效果跟真的硬體觸發一致。
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
from dashboard_html import DASHBOARD_HTML
from main import Companion
from memory.retrieve import search
from protocol import TouchEvent

app = FastAPI(title="ai-pc-agent-debug")
companion = Companion()


@app.on_event("startup")
async def _start_companion() -> None:
    asyncio.create_task(companion.run())


class GestureRequest(BaseModel):
    kind: str = "double_tap"
    strength: float = 1.0
    dur_ms: int = 200


@app.post("/debug/gesture")
async def debug_gesture(req: GestureRequest):
    """假裝 ESP32 送了一個手勢事件，不用真的壓 FSR。"""
    companion._on_esp32_event(TouchEvent(kind=req.kind, strength=req.strength, dur_ms=req.dur_ms))
    return {"ok": True, "kind": req.kind}


class UtteranceRequest(BaseModel):
    text: str


@app.post("/debug/utterance")
async def debug_utterance(req: UtteranceRequest):
    """直接注入一句「使用者說的話」，跳過麥克風 + STT，直接觸發對話回覆那條路徑。"""
    companion._on_final_utterance(req.text)
    return {"ok": True}


@app.post("/debug/screenshot")
async def debug_screenshot():
    """立刻強制跑一次「截圖 -> /v1/screen-observations -> 寫記憶」，不等排程。"""
    import screen_watcher

    agent = screen_watcher.build_agent()
    agent.memory = companion.memory  # 跟常駐的 Companion 共用同一個記憶庫，方便驗證
    agent.client = companion.mi300   # 共用同一個已經接好 trace 的 client，dashboard 才看得到這次呼叫
    state = agent.run_once(now=time.monotonic())
    return {"ok": True, "foreground": state.get("foreground")}


@app.post("/debug/homework")
async def debug_homework(
    image: UploadFile = File(...),
    transcript: str = Form(""),
    send_to_chatgpt: bool = Form(False),
):
    """用上傳的測試圖片＋文字稿，直接跑作業分析流程（不用真的雙擊 FSR、不用真的拍照）。
    預設不送去 ChatGPT（send_to_chatgpt=false），只驗證到 chatgpt_prompt 產生為止。
    是 multipart/form-data（要帶檔案），所以其他欄位用 Form(...) 而不是 JSON body——
    兩者混用在 FastAPI 裡不可靠，個別 Form 欄位才是穩定跨版本的寫法。"""
    image_bytes = await image.read()
    result = companion.mi300.analyze_homework(image_bytes, transcript)
    companion.memory.add_or_extend("homework", result["analysis"], state_key="")
    if send_to_chatgpt:
        companion.chatgpt.send_prompt(result["chatgpt_prompt"])
    return result


@app.get("/debug/status")
async def debug_status():
    esp32_connected = companion.esp32._ws is not None
    mi300_ok = False
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(config.MI300_BASE_URL.rstrip("/") + "/health")
            mi300_ok = resp.status_code == 200
    except httpx.HTTPError:
        pass
    recent = companion.memory.recent(1)
    return {
        "esp32_ws_connected": esp32_connected,
        "mi300_reachable": mi300_ok,
        "last_memory_write_ts": recent[0].ts_end if recent else None,
        # 【觸覺】最近手勢：ESP32 上一次回報的動作（squeeze/pat/shake/lift/putdown/
        # double_tap），會被塞進下一次對話回覆的 prompt。沒有任何手勢事件時是 null。
        "last_touch": companion.state.last_touch,
    }


@app.get("/debug/memory/recent")
async def debug_memory_recent(n: int = 10):
    return [
        {
            "id": m.id, "ts_start": m.ts_start, "ts_end": m.ts_end, "level": m.level,
            "source": m.source, "app": m.app, "text": m.text, "error_sig": m.error_sig,
            "importance": m.importance,
        }
        for m in companion.memory.recent(n)
    ]


# ---------------------------------------------------------------------------
# 測試 memory retrieval（hybrid vector+BM25，見 ai-pc-agent/memory/retrieve.py）
# 用假資料驗證排序/decay/重要度合不合理，不用真的講很多話、等很多天。
# ---------------------------------------------------------------------------
# (source, text, app, state_key, error_sig, 幾小時前)——故意混雜可以被關鍵字
# 命中（KeyError）跟只能靠語意命中（累/休息 vs 早點睡）的例子，也跨不同新舊
# 程度，方便看時間衰減有沒有作用。
SEED_MEMORIES = [
    ("screen", "在 main.py 遇到 KeyError: 'response'", "code", "code|main.py|KeyError", "KeyError", 72),
    ("speech", "這個 KeyError 到底怎麼修，我試了好幾次都不對", "", "", "KeyError", 71.9),
    ("reply", "KeyError 通常是 key 拼錯，要不要先印出 dict 看看？", "", "", "KeyError", 71.8),
    ("screen", "在寫 ESP32 韌體，測試 WiFi WebSocket 連線", "platformio", "platformio|s9_wifi_sensors|", "", 24),
    ("screen", "在看 YouTube 影片", "chrome", "chrome|YouTube|", "", 5),
    ("speech", "我今天好累，想早點休息", "", "", "", 2),
    ("touch", "使用者squeeze", "", "", "", 1),
    ("homework", "題目：求 f(x)=x^2 sin(x) 的導函數。使用者已寫：f'(x)=2x sin(x)，卡在乘法微分那步", "", "", "", 0.5),
]


@app.post("/debug/memory/seed")
async def debug_memory_seed():
    """插入一批固定的假記憶，方便測試 retrieval 排序/decay/重要度。每次呼叫都是
    新增（不是覆蓋），重複呼叫會疊加多份一樣的資料——測完想清乾淨就打
    /debug/memory/clear。"""
    now = datetime.now().astimezone()
    inserted = []
    for source, text, app, state_key, error_sig, hours_ago in SEED_MEMORIES:
        ts = (now - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
        mid = companion.memory.add_or_extend(source, text, app=app, state_key=state_key, error_sig=error_sig, ts=ts)
        inserted.append({"id": mid, "source": source, "text": text, "ts": ts})
    return {"ok": True, "inserted": inserted}


@app.delete("/debug/memory/clear")
async def debug_memory_clear():
    """清空所有記憶（含 seed 的假資料跟你自己測試留下的資料）。不可回復，只給
    本機測試用，正式資料不會這樣清。"""
    companion.memory.clear_all()
    return {"ok": True}


@app.get("/debug/retrieve")
async def debug_retrieve(query: str, k: int = 5):
    """測試 hybrid retrieval：給一句查詢，回傳排序後的相關記憶＋分數拆解
    （vector/text/decay/importance），方便判斷排序合不合理，不用真的跑一次
    完整對話回覆才看得到【相關記憶】揀了什麼。"""
    hits = search(companion.memory, query, k=k)
    return [
        {
            "id": h.memory.id,
            "memory_text": h.memory.text,
            "source": h.memory.source,
            "ts_end": h.memory.ts_end,
            "score": h.score,
            "vector_score": h.vector,
            "text_score": h.text,
            "decay": h.decay,
            "importance": h.memory.importance,
        }
        for h in hits
    ]


@app.get("/debug/trace")
async def debug_trace(n: int = 30):
    """給 dashboard 看的「傳了什麼、收到什麼」紀錄，見 trace_log.py。"""
    return [entry.to_dict() for entry in companion.trace.recent(n)]


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

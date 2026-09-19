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

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import config
from dashboard_html import DASHBOARD_HTML
from main import Companion
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


@app.get("/debug/trace")
async def debug_trace(n: int = 30):
    """給 dashboard 看的「傳了什麼、收到什麼」紀錄，見 trace_log.py。"""
    return [entry.to_dict() for entry in companion.trace.recent(n)]


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

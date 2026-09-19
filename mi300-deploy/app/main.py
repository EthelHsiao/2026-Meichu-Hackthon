"""
陪碼 MI300 推論服務。

2026-09-19 範圍異動：原本只做 /parse-timer、/affect-label 兩個無狀態呼叫
（對應 HACKATHON_PROPOSAL_SPEC.md 第 4 節）。現在加入螢幕內容摘要與記憶結構，
這是刻意的範圍擴大，不是原本 spec 就定義的 MVP——決策記錄見
claude/HACKATHON_PROPOSAL_SPEC.md 新增的「範圍異動」節。

架構：
- AI PC 定期截圖、轉 base64，POST 給 /events/screen；原始圖片只在這支
  process 記憶體裡短暫存在（呼叫 Ollama 用完即丟），落地存的只有文字描述。
- AI PC 也可以直接 POST 一句話（使用者口述、agent 狀態變化）到 /events/note。
- 背景 task 每隔 SUMMARY_REFRESH_SECONDS 秒，把最近事件摘要成幾句話，
  存進 state 表，/status 直接讀這個 cache（給 dashboard 高頻率 poll 用，
  不會每次都重新呼叫 LLM）。
- /status 同時是 dashboard 的資料來源，也是 AI PC 之後如果要拿「目前情境」
  的地方。
"""
import asyncio
import os
import re
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="peima-mi300-api")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
TEXT_MODEL = os.environ.get("TEXT_MODEL", "qwen2.5:7b-instruct")
# 2026-09-19 從 llava:7b 換成 minicpm-v：同樣大小的下載（5.5GB），但實測讀
# 螢幕小字/終端機錯誤訊息準確度高很多——拿模擬的 VS Code + Python
# KeyError traceback 截圖測試，llava:7b 會編造錯誤類型（幻覺成
# NameError、還編出不存在的 sklearn），minicpm-v 正確讀出
# "KeyError: 'response'"，速度還比 llava:34b 快超過一倍。
# 有試過 llama3.2-vision（理論上更新的架構），但這個 Ollama 版本會報
# "unknown model architecture: 'mllama'"，裝了最新版 Ollama 還是一樣，
# 這台機器目前跑不動那個架構，不是 VRAM 或安裝設定的問題。
VISION_MODEL = os.environ.get("VISION_MODEL", "minicpm-v")
DB_PATH = os.environ.get("MEMORY_DB_PATH", "/mlsteam/workspace/memory.db")
SUMMARY_REFRESH_SECONDS = int(os.environ.get("SUMMARY_REFRESH_SECONDS", "60"))
RECENT_EVENTS_FOR_SUMMARY = int(os.environ.get("RECENT_EVENTS_FOR_SUMMARY", "30"))
# restart_service.sh 在每次部署時塞進來的 commit/時間戳，用來在 /health 跟
# dashboard 上證明「這次 push 真的換成新版本了」，不用去翻 GitHub Actions。
DEPLOY_SHA = os.environ.get("DEPLOY_SHA", "unknown")
DEPLOY_TIME = os.environ.get("DEPLOY_TIME", "unknown")


# ---------------------------------------------------------------------------
# 儲存層：一個 SQLite 檔案，放在 /mlsteam/workspace 底下（唯一 LAB 重開還在的路徑）
# ---------------------------------------------------------------------------
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                source TEXT NOT NULL,
                text TEXT NOT NULL
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                value TEXT
            )"""
        )
        db.commit()


def save_event(source: str, text: str) -> str:
    ts = datetime.now(timezone.utc).isoformat()
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.execute("INSERT INTO events (ts, source, text) VALUES (?, ?, ?)", (ts, source, text))
        db.commit()
    return ts


def recent_events(limit: int):
    with closing(sqlite3.connect(DB_PATH)) as db:
        rows = db.execute(
            "SELECT ts, source, text FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return list(reversed(rows))


def get_state(key: str, default: str = "") -> str:
    with closing(sqlite3.connect(DB_PATH)) as db:
        row = db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def set_state(key: str, value: str) -> None:
    with closing(sqlite3.connect(DB_PATH)) as db:
        db.execute(
            "INSERT INTO state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        db.commit()


init_db()


# ---------------------------------------------------------------------------
# Ollama 呼叫
# ---------------------------------------------------------------------------
async def call_ollama_generate(
    model: str, prompt: str, max_tokens: int = 64, images=None, temperature: float = 0.3
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    if images:
        payload["images"] = images
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"ollama unreachable: {exc}") from exc
        return resp.json().get("response", "")


@app.get("/health")
async def health():
    return {
        "ok": True,
        "text_model": TEXT_MODEL,
        "vision_model": VISION_MODEL,
        "ollama_url": OLLAMA_URL,
        "deploy_sha": DEPLOY_SHA,
        "deploy_time": DEPLOY_TIME,
    }


# ---------------------------------------------------------------------------
# 原本就有的兩個呼叫（HACKATHON_PROPOSAL_SPEC.md 第 4 節）
# ---------------------------------------------------------------------------
class TimerRequest(BaseModel):
    utterance: str


class AffectRequest(BaseModel):
    agent_name: str = "coding agent"
    elapsed_minutes: float
    status: str  # "running" | "needs_confirmation" | "finished"
    exit_code: Optional[int] = None


@app.post("/parse-timer")
async def parse_timer(req: TimerRequest):
    prompt = (
        "你是一個計時器解析器。從下面這句話擷取使用者想要休息的分鐘數，"
        '只回傳一個 JSON，格式為 {"minutes": <整數>}，不要有其他文字或說明。\n'
        f"句子：{req.utterance}\nJSON："
    )
    raw = await call_ollama_generate(TEXT_MODEL, prompt, max_tokens=32)
    match = re.search(r'\{[^{}]*"minutes"[^{}]*\}', raw)
    if not match:
        return {"minutes": None, "raw": raw}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"minutes": None, "raw": raw}


@app.post("/affect-label")
async def affect_label(req: AffectRequest):
    status_text = {
        "running": f"{req.agent_name} 已經執行了 {req.elapsed_minutes:.0f} 分鐘，還在跑",
        "needs_confirmation": f"{req.agent_name} 需要你確認一些事情",
        "finished": f"{req.agent_name} 結束了，exit code {req.exit_code}",
    }.get(req.status, f"{req.agent_name} 狀態不明")

    prompt = (
        "你是一個安靜、簡短、不說教的桌面陪伴角色。"
        "用一句不超過 15 個字的中文，準確標記使用者目前的等待狀態，"
        "不要建議使用者做什麼、不要分析問題原因、不要加驚嘆號堆疊。\n"
        f"狀態：{status_text}\n一句話："
    )
    raw = (await call_ollama_generate(TEXT_MODEL, prompt, max_tokens=48)).strip().strip('"')
    set_state("last_reflection", raw)
    save_event("agent-status", status_text)
    return {"reflection": raw}


# ---------------------------------------------------------------------------
# 2026-09-19 新增：螢幕摘要 + 記憶事件
# ---------------------------------------------------------------------------
class ScreenEvent(BaseModel):
    image_b64: str  # AI PC 端截圖後 base64 編碼傳過來；這支 process 用完即丟，不落地存圖


@app.post("/events/screen")
async def ingest_screen(evt: ScreenEvent):
    # 兩段式：先用 vision model 產生英文描述（多數 vision model 對英文比較穩），
    # 再用 text model 轉成精簡繁中一句話——比要求 vision model 直接輸出中文更可靠。
    # temperature=0（不是預設的 0.3）：這是「讀畫面上寫了什麼」的任務，
    # 要準確不要有創意。實測同一張測試截圖，0.3 大概 1/3 機率會漏掉螢幕上
    # 明明看得到的錯誤訊息，0.0 連續多次都穩定讀對。
    caption_en = await call_ollama_generate(
        VISION_MODEL,
        "Describe in 1-2 short sentences what the user is doing on screen "
        "(e.g. which app or file they're working in). If an error, exception, "
        "or traceback is visible in a terminal/console, mention the error type "
        "and message; otherwise don't speculate about errors or mood.",
        max_tokens=96,
        images=[evt.image_b64],
        temperature=0.0,
    )
    zh_prompt = (
        "把下面這句英文描述，改寫成不超過 40 個字的繁體中文，保留提到的錯誤"
        "類型/訊息（如果有的話），不要加多餘文字：\n" + caption_en.strip() + "\n繁體中文："
    )
    caption_zh = (await call_ollama_generate(TEXT_MODEL, zh_prompt, max_tokens=80)).strip()
    ts = save_event("screen", caption_zh)
    return {"ts": ts, "caption": caption_zh}


class NoteEvent(BaseModel):
    text: str
    source: str = "utterance"  # "utterance" | "agent-status" | 其他自訂來源


@app.post("/events/note")
async def ingest_note(evt: NoteEvent):
    ts = save_event(evt.source, evt.text)
    return {"ts": ts}


@app.get("/status")
async def status():
    events = recent_events(10)
    return {
        "summary": get_state("summary", "（還沒有足夠事件可以摘要）"),
        "last_reflection": get_state("last_reflection", ""),
        "recent_events": [{"ts": ts, "source": src, "text": text} for ts, src, text in events],
        "deploy_sha": DEPLOY_SHA,
        "deploy_time": DEPLOY_TIME,
    }


async def summarize_loop():
    while True:
        await asyncio.sleep(SUMMARY_REFRESH_SECONDS)
        events = recent_events(RECENT_EVENTS_FOR_SUMMARY)
        if not events:
            continue
        joined = "\n".join(f"[{ts}] ({src}) {text}" for ts, src, text in events)
        prompt = (
            "以下是使用者最近的活動紀錄（螢幕描述、口述、agent 狀態）。"
            "整理成最多 3 條繁體中文短句，代表使用者目前在做的事跟狀態，"
            "不要條列細節、不要臆測情緒。\n\n" + joined + "\n\n摘要："
        )
        try:
            summary = await call_ollama_generate(TEXT_MODEL, prompt, max_tokens=120)
            set_state("summary", summary.strip())
        except Exception as exc:  # noqa: BLE001 — 背景 loop，記 log 就好，不能整個死掉
            print(f"[summarize_loop] 失敗: {exc}")


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(summarize_loop())


# ---------------------------------------------------------------------------
# 展示用 dashboard（沒有真的帳號密碼登入——只是給評審看的狀態頁，見 README 說明）
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>陪碼 — 現況</title>
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, "PingFang TC", "Noto Sans TC", sans-serif;
         background: #0f1115; color: #e6e6e6; margin: 0; padding: 24px; }
  h1 { font-size: 20px; font-weight: 600; margin-bottom: 4px; }
  .sub { color: #9aa0a6; font-size: 13px; margin-bottom: 4px; }
  .tagline { color: #7dd3fc; font-size: 13px; margin-bottom: 16px; }
  .card { background: #1a1d24; border-radius: 12px; padding: 16px 20px; margin-bottom: 16px; }
  .card h2 { font-size: 13px; color: #9aa0a6; margin: 0 0 8px; font-weight: 500; }
  .summary { font-size: 16px; line-height: 1.6; white-space: pre-line; }
  .reflection { font-size: 18px; font-style: italic; color: #7dd3fc; }
  .events { list-style: none; margin: 0; padding: 0; font-size: 13px; }
  .events li { padding: 6px 0; border-top: 1px solid #262a33; display: flex; gap: 10px; }
  .events li:first-child { border-top: none; }
  .ts { color: #6b7280; white-space: nowrap; }
  .src { color: #7dd3fc; white-space: nowrap; }
  .dot { display:inline-block; width:8px; height:8px; border-radius:50%; background:#22c55e; margin-right:6px; }
</style>
</head>
<body>
  <h1><span class="dot"></span>陪碼</h1>
  <div class="tagline">知道你在忙、卡關、還是該休息了</div>
  <div class="sub" id="updated">連線中...</div>
  <div class="sub" id="deploy">—</div>

  <div class="card">
    <h2>目前狀態摘要</h2>
    <div class="summary" id="summary">—</div>
  </div>

  <div class="card">
    <h2>最新一句反映</h2>
    <div class="reflection" id="reflection">—</div>
  </div>

  <div class="card">
    <h2>最近事件</h2>
    <ul class="events" id="events"></ul>
  </div>

<script>
async function tick() {
  try {
    const res = await fetch('/status');
    const data = await res.json();
    document.getElementById('summary').textContent = data.summary || '（尚無摘要）';
    document.getElementById('reflection').textContent = data.last_reflection || '（尚無反映）';
    const ul = document.getElementById('events');
    ul.innerHTML = '';
    (data.recent_events || []).slice().reverse().forEach(e => {
      const li = document.createElement('li');
      const t = new Date(e.ts).toLocaleTimeString('zh-TW', { hour12: false });
      li.innerHTML = `<span class="ts">${t}</span><span class="src">${e.source}</span><span>${e.text}</span>`;
      ul.appendChild(li);
    });
    document.getElementById('updated').textContent = '最後更新 ' + new Date().toLocaleTimeString('zh-TW', { hour12: false });
    document.getElementById('deploy').textContent = `版本 ${data.deploy_sha || '未知'} · 部署於 ${data.deploy_time || '未知'}`;
  } catch (e) {
    document.getElementById('updated').textContent = '連線失敗，重試中...';
  }
}
tick();
setInterval(tick, 3000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

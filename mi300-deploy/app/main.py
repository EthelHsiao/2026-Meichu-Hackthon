"""
陪碼 MI300 推論服務 — 只做 HACKATHON_PROPOSAL_SPEC.md 第 4 節明確定義的兩件事：
  1. /parse-timer   自然語言 -> 休息分鐘數（U04）
  2. /affect-label  等待 agent 時的一句準確標記反映（第 6.1 節「陪你等 agent」）

刻意不接受螢幕內容、程式碼或原始文字工作內容 —— 只吃結構化摘要，
呼應 spec 第 9 節「AI PC 只傳結構化摘要，不傳敏感內容」的隱私設計。
"""
import json
import os
import re
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="peima-mi300-api")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL_NAME = os.environ.get("MODEL_NAME", "qwen2.5:7b-instruct")


class TimerRequest(BaseModel):
    utterance: str


class AffectRequest(BaseModel):
    agent_name: str = "coding agent"
    elapsed_minutes: float
    status: str  # "running" | "needs_confirmation" | "finished"
    exit_code: Optional[int] = None


async def call_ollama(prompt: str, max_tokens: int = 64) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": MODEL_NAME,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": 0.3},
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"ollama unreachable: {exc}") from exc
        return resp.json().get("response", "")


@app.get("/health")
async def health():
    return {"ok": True, "model": MODEL_NAME, "ollama_url": OLLAMA_URL}


@app.post("/parse-timer")
async def parse_timer(req: TimerRequest):
    """U04：「我好累，想睡半小時」-> {"minutes": 30}"""
    prompt = (
        "你是一個計時器解析器。從下面這句話擷取使用者想要休息的分鐘數，"
        '只回傳一個 JSON，格式為 {"minutes": <整數>}，不要有其他文字或說明。\n'
        f"句子：{req.utterance}\nJSON："
    )
    raw = await call_ollama(prompt, max_tokens=32)
    match = re.search(r'\{[^{}]*"minutes"[^{}]*\}', raw)
    if not match:
        return {"minutes": None, "raw": raw}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"minutes": None, "raw": raw}


@app.post("/affect-label")
async def affect_label(req: AffectRequest):
    """「陪你等 agent」情境的 affect labeling 反映（Lieberman et al. 2007 依據，見 spec 第 3 節）。"""
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
    raw = await call_ollama(prompt, max_tokens=48)
    return {"reflection": raw.strip().strip('"')}

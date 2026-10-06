"""
桌寵 MI300 推論服務。

2026-09-20 範圍異動：依照 `docs/api.html` 定案的合約，換成三支無狀態推論
API（螢幕觀察、對話回覆、作業拍照分析），拿掉本機 SQLite。決策記錄：

- 記憶（RAG、壓縮、profile）已經確定放在 AIPC 端（`ai-pc-agent/memory/`），
  這裡不應該再重複存一份、更不應該是「唯一一份」——之前 `events`/`state`
  兩個表只是這支服務自己的 demo dashboard 資料，跟 AIPC 的記憶系統是兩個
  各自獨立、互相沒有同步的資料庫，容易搞混，所以直接移除。
- 這支服務只做一件事：收 request、呼叫本機 Ollama、把模型輸出整理成固定
  JSON 格式回傳。原始圖片、逐字稿只在這個 process 記憶體裡短暫存在，
  用完即丟，不落地、不快取、重啟就什麼都不剩。
- `/analyze/screen`、`/models`、`/model-lab*` 這幾支是模型評測/除錯工具
  （`feat/mi300-model-lab` 分支的成果，2026-09-19 手動部署上去、原本沒有
  進 git），跟上面的記憶議題無關、本身也是無狀態的，保留下來繼續當
  `mi300-deploy/app/model_lab.html`／`mi300-deploy/bench/` 的後端。
- 2026-09-20：`/v1/screen-observations` 改用跟 model-lab 同一份
  `bench/screen-schema.json`／`screen-prompt.txt`（app/activity/evidence/
  error/cause/missing_context），取代原本兩段式 caption+翻譯產生的
  `{"text","error"}` 極簡格式——避免正式線上跟 bench 評測各自維護一份
  prompt/schema。呼叫端見 `ai-pc-agent/observation_models.py`。
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="peima-mi300-api")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
TEXT_MODEL = os.environ.get("TEXT_MODEL", "qwen2.5:7b-instruct")
# 模型選擇持久化在 git checkout 之外（LAB 重開後、程式重新部署後都還在）；
# 環境變數優先於設定檔。目前正式部署用的視覺模型是 qwen3.6:35b-a3b-q8_0，
# 見 mi300-deploy/bench/DEPLOYED_MODEL.md 的實測比較記錄。
MODEL_CONFIG_PATH = os.environ.get("MODEL_CONFIG_PATH", "/mlsteam/workspace/model-config.json")
model_config = json.loads(Path(MODEL_CONFIG_PATH).read_text(encoding="utf-8")) if Path(MODEL_CONFIG_PATH).exists() else {}
VISION_MODEL = os.environ.get("VISION_MODEL", model_config.get("vision_model", "qwen3.6:35b-a3b-q8_0"))
VISION_THINK = model_config.get("vision_think")
VISION_KEEP_ALIVE = model_config.get("vision_keep_alive", "60m")
if VISION_THINK is not None and not isinstance(VISION_THINK, bool):
    raise ValueError("model-config.json: vision_think must be a boolean or null")
BENCH_DIR = Path(__file__).resolve().parent.parent / "bench"
APP_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
# restart_service.sh 在每次部署時塞進來的 commit/時間戳，用來在 /health 上
# 證明「這次 push 真的換成新版本了」，不用去翻 GitHub Actions。
DEPLOY_SHA = os.environ.get("DEPLOY_SHA", "unknown")
DEPLOY_TIME = os.environ.get("DEPLOY_TIME", "unknown")

# 跟 ai-pc-agent/protocol.py 的 EXPRESSIONS 保持一致——這兩份是各自獨立部署
# 的服務（AIPC / MI300），不共用 Python package，所以各自定義一份，改動時
# 兩邊要一起改。LCD 韌體目前只畫得出其中 6 種，見 esp32-bringup 的待辦。
EXPRESSIONS = ("neutral", "happy", "joy", "love", "sad", "sleepy", "surprised", "thinking", "worried")
# 每個值都明確帶引號——實測 qwen2.5:7b-instruct 在只列裸字時，偶爾會漏加引號
# 輸出成不合法 JSON（例如 {"expr": neutral, ...}），連帶讓整個回覆退化成 fallback。
_EXPR_LIST = ", ".join(f'"{e}"' for e in EXPRESSIONS)


# ---------------------------------------------------------------------------
# Ollama 呼叫
# ---------------------------------------------------------------------------
async def call_ollama_result(
    model: str, prompt: str, max_tokens: int = 64, images=None, temperature: float = 0.3,
    think: Optional[bool] = None, output_schema: Optional[dict] = None,
) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    if images:
        payload["images"] = images
    if think is not None:
        payload["think"] = think
    if output_schema is not None:
        payload["format"] = output_schema
    if images:
        payload["options"]["num_ctx"] = 8192
        # 讓主視覺模型保持載入狀態（避免每次上傳都要冷啟動）；一次性的模型比較呼叫用完就放。
        payload["keep_alive"] = VISION_KEEP_ALIVE if model == VISION_MODEL else 0
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"ollama unreachable: {exc}") from exc
        result = resp.json()
        if result.get("error"):
            raise HTTPException(status_code=502, detail=result["error"])
        result["client_total_seconds"] = time.perf_counter() - started
        return result


async def call_ollama_generate(
    model: str, prompt: str, max_tokens: int = 64, images=None, temperature: float = 0.3,
    think: Optional[bool] = None,
) -> str:
    result = await call_ollama_result(model, prompt, max_tokens, images, temperature, think)
    return result.get("response", "")


def _extract_json(raw: str) -> Optional[dict]:
    """模型有時候會在 JSON 前後夾雜文字或 markdown code fence，取第一個 {...} 區塊。
    也修一個實測遇到的常見錯誤：模型把列舉值當成裸字漏加引號輸出，例如
    {"expr": neutral, "text": "..."}——先試嚴格解析，失敗才試補引號重解一次，
    不因為這種小失誤就整個 fallback。"""
    match = re.search(r"\{.*\}", raw, re.S)
    if not match:
        return None
    candidate = match.group(0)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r':\s*([A-Za-z_][A-Za-z0-9_]*)\s*([,}])', r': "\1"\2', candidate)
        try:
            parsed = json.loads(repaired)
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


@app.get("/health")
async def health():
    return {
        "ok": True,
        "text_model": TEXT_MODEL,
        "vision_model": VISION_MODEL,
        "vision_think": VISION_THINK,
        "vision_keep_alive": VISION_KEEP_ALIVE,
        "app_sha256": APP_SHA256,
        "ollama_url": OLLAMA_URL,
        "deploy_sha": DEPLOY_SHA,
        "deploy_time": DEPLOY_TIME,
    }


# ---------------------------------------------------------------------------
# POST /v1/screen-observations —— 截圖 -> 結構化畫面觀察
# 格式見 docs/api.html §③、ai-pc-agent/observation_models.py。
# ---------------------------------------------------------------------------
class ScreenObservationRequest(BaseModel):
    observation: dict
    image_b64: str


def _load_screen_prompt_and_schema() -> tuple[str, dict]:
    """跟 /model-lab/defaults 讀同一份 bench 檔案，正式線上跟評測用同一份
    prompt/schema，不用各自維護一份。每次請求讀檔（而不是模組載入時快取一份）
    是刻意的：改 bench/screen-prompt.txt 調 prompt 用詞時不用重新部署就生效，
    跟 model-lab 現有的行為一致。"""
    return (
        (BENCH_DIR / "screen-prompt.txt").read_text(encoding="utf-8-sig"),
        json.loads((BENCH_DIR / "screen-schema.json").read_text(encoding="utf-8-sig")),
    )


_SCREEN_OBSERVATION_FALLBACK = {
    "app": None, "activity": None, "evidence": [], "error": None,
    "cause": None, "missing_context": [],
}


def _coerce_screen_observation(parsed: object) -> dict:
    """Ollama 的 structured output（`format`=schema）應該已經強制模型輸出合法
    形狀，這裡只是保底：万一模型整個沒回 JSON、或漏了某個 top-level 欄位，
    照樣回一個符合合約形狀的物件，不讓呼叫端要處理「這支 API 有時候會少欄位」
    這種例外。"""
    if not isinstance(parsed, dict):
        parsed = {}
    return {
        "app": parsed.get("app") if isinstance(parsed.get("app"), str) else None,
        "activity": parsed.get("activity") if isinstance(parsed.get("activity"), str) else None,
        "evidence": parsed.get("evidence") if isinstance(parsed.get("evidence"), list) else [],
        "error": parsed.get("error") if isinstance(parsed.get("error"), dict) else None,
        "cause": parsed.get("cause") if isinstance(parsed.get("cause"), dict) else None,
        "missing_context": parsed.get("missing_context") if isinstance(parsed.get("missing_context"), list) else [],
    }


@app.post("/v1/screen-observations")
async def create_screen_observation(req: ScreenObservationRequest):
    # temperature=0：這是「讀畫面上寫了什麼」的任務，要準確不要有創意（見
    # bench/DEPLOYED_MODEL.md 的實測記錄）。max_tokens=768 跟 /analyze/screen
    # 的預設值一樣——這份 schema 比舊版 {"text","error"} 豐富很多，128 這種
    # 小顆的 token 數會在 evidence/cause 生完前就被截斷，導致 JSON 解不出來。
    prompt, schema = _load_screen_prompt_and_schema()
    result = await call_ollama_result(
        VISION_MODEL, prompt, max_tokens=768, images=[req.image_b64], temperature=0.0,
        think=VISION_THINK, output_schema=schema,
    )
    try:
        parsed = json.loads(result.get("response", ""))
    except (json.JSONDecodeError, TypeError):
        parsed = None
    return _coerce_screen_observation(parsed)


# ---------------------------------------------------------------------------
# POST /v1/chat/completions —— OpenAI 相容格式，對話回覆
# 刻意沿用這個命名（不是 /v1/replies 之類的資源式命名），這樣可以直接用
# 任何 OpenAI SDK / 工具測試，且跟 Ollama 生態相容。格式見 docs/api.html §④。
# ---------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = TEXT_MODEL
    messages: list[ChatMessage]
    response_format: Optional[dict] = None


def _fallback_reply(raw_text: str) -> dict:
    return {"expr": "neutral", "text": (raw_text.strip() or "嗯，我在聽")[:40]}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    # req.model 之前一直沒有真的被用到（不管傳什麼都硬跑 TEXT_MODEL）——
    # 2026-09-20 為了比較 7B/35B 回覆品質跟延遲才發現、修正。預設值仍是
    # TEXT_MODEL，不傳 model 欄位的呼叫端行為不變。
    model = req.model or TEXT_MODEL
    # qwen3.6:35b 預設會開 thinking mode——不明確關掉的話，模型會把整個
    # num_predict 額度拿去生看不見的推理過程，"response" 欄位直接是空字串
    # （推理內容全跑進另一個 "thinking" 欄位），導致每次都 fallback、而且
    # 慢了 20+ 倍。這裡改成跟 /v1/screen-observations、/v1/homework-analyses
    # 一致的做法：用到 VISION_MODEL 就沿用同一份 VISION_THINK 設定。
    think = VISION_THINK if model == VISION_MODEL else False
    system = "\n".join(m.content for m in req.messages if m.role == "system")
    user = "\n".join(m.content for m in req.messages if m.role == "user")
    prompt = f"{system}\n\n{user}\n只回傳 JSON，不要其他文字或 markdown："
    started = time.perf_counter()
    raw = await call_ollama_generate(model, prompt, max_tokens=160, temperature=0.4, think=think)
    elapsed = time.perf_counter() - started

    parsed = _extract_json(raw)
    if not parsed or not isinstance(parsed.get("text"), str) or not parsed["text"].strip():
        parsed = _fallback_reply(raw)
    if parsed.get("expr") not in EXPRESSIONS:
        parsed["expr"] = "neutral"
    parsed["text"] = parsed["text"].strip()[:40]

    content = json.dumps(parsed, ensure_ascii=False)
    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "model": model,
        "timing_seconds": elapsed,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
        ],
    }


# ---------------------------------------------------------------------------
# POST /v1/homework-analyses —— 作業拍照分析（FSR1 雙擊流程用，見 docs/api.html §⑥）
# 跟上面的螢幕觀察分開：這裡要求逐字轉錄，不是一句話 caption，也不解題。
# ---------------------------------------------------------------------------
HOMEWORK_ANALYSIS_PROMPT = (
    "你是一個仔細的手寫作業辨識器。分析附圖，盡量逐字轉錄圖片中的題目文字，"
    "以及使用者已經寫下的解題過程，包含數學算式與符號（用文字或常見記法還原，"
    "例如 x^2、a/b、積分寫成 integral of ...）。不要嘗試解題或補完使用者沒寫的"
    "部分，也不要臆測看不清楚的字——看不清楚就標註「(看不清楚)」。用繁體中文回答。"
)


class HomeworkAnalysisRequest(BaseModel):
    image_b64: str
    transcript: str = ""


@app.post("/v1/homework-analyses")
async def create_homework_analysis(req: HomeworkAnalysisRequest):
    analysis = (
        await call_ollama_generate(
            VISION_MODEL, HOMEWORK_ANALYSIS_PROMPT, max_tokens=512, images=[req.image_b64], temperature=0.0,
            think=VISION_THINK,
        )
    ).strip()

    reassurance_prompt = (
        "你是一個溫暖、簡短、不說教的桌面陪伴角色。使用者剛剛拍了一張作業/習題"
        "照片並對你抱怨遇到的困難。以下是這張圖片的詳細內容分析，以及使用者說的話。"
        "請用最多兩句、不超過 40 字的繁體中文給使用者情緒支持/鼓勵，不要嘗試解題，"
        "只回傳一個 JSON，兩個欄位都要用雙引號包住字串值，例如：\n"
        '{"expr": "happy", "text": "算對了，很棒！"}\n'
        f"expr 的值只能是以下其中之一（要帶雙引號）：{_EXPR_LIST}。\n"
        f"圖片分析：{analysis}\n使用者說的話：{req.transcript or '（沒有額外說明）'}\nJSON："
    )
    raw = await call_ollama_generate(TEXT_MODEL, reassurance_prompt, max_tokens=120)
    parsed = _extract_json(raw)
    if parsed and isinstance(parsed.get("text"), str) and parsed["text"].strip():
        reassurance = {
            "expr": parsed.get("expr") if parsed.get("expr") in EXPRESSIONS else "neutral",
            "text": parsed["text"].strip()[:40],
        }
    else:
        reassurance = {"expr": "neutral", "text": "辛苦了，我陪你一起看看。"}

    chatgpt_prompt_text = (
        "以下是我卡住的題目跟我目前的解法，請幫我看看哪裡有問題、給我下一步的提示"
        "（不用直接給答案）：\n\n"
        f"題目/已寫內容：\n{analysis}\n\n我的狀況：{req.transcript or '（沒有額外說明）'}"
    )
    return {"analysis": analysis, "reassurance": reassurance, "chatgpt_prompt": chatgpt_prompt_text}


# ---------------------------------------------------------------------------
# 模型評測/除錯工具（feat/mi300-model-lab 分支的成果，2026-09-19 手動部署上去，
# 這次順便補進 git）。無狀態、不寫記憶，跟上面的正式合約互不影響。
# ---------------------------------------------------------------------------
class ScreenAnalysisRequest(BaseModel):
    image_b64: str
    prompt: str
    model: Optional[str] = None
    output_schema: Optional[dict] = Field(default=None, alias="schema")
    max_tokens: int = Field(default=768, ge=1, le=4096)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    think: Optional[bool] = None


@app.post("/analyze/screen")
async def analyze_screen(req: ScreenAnalysisRequest):
    """Stateless prompt/image experiments; no event or memory writes."""
    model = req.model or VISION_MODEL
    think = req.think
    if think is None and model == VISION_MODEL:
        think = VISION_THINK
    result = await call_ollama_result(
        model, req.prompt, req.max_tokens, [req.image_b64], req.temperature,
        think=think, output_schema=req.output_schema,
    )
    response = result.get("response", "")
    try:
        parsed = json.loads(response)
        json_valid = True
    except ValueError:
        parsed, json_valid = None, False
    return {
        "model": model, "response": response, "parsed_json": parsed,
        "json_valid": json_valid,  # Syntax only; caller must validate its schema/semantics.
        "done_reason": result.get("done_reason"),
        "thinking": result.get("thinking", ""),
        "client_total_seconds": result["client_total_seconds"],
        "timing_seconds": {key: result[key] / 1e9 for key in (
            "total_duration", "load_duration", "prompt_eval_duration", "eval_duration"
        ) if key in result},
        "eval_count": result.get("eval_count"),
    }


@app.get("/models")
async def available_models():
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"default": VISION_MODEL, "models": response.json().get("models", [])}


@app.get("/model-lab", response_class=HTMLResponse)
async def model_lab():
    return Path(__file__).with_name("model_lab.html").read_text(encoding="utf-8")


@app.get("/model-lab/defaults")
async def model_lab_defaults():
    bench = Path(__file__).resolve().parent.parent / "bench"
    return {
        "prompt": (bench / "screen-prompt.txt").read_text(encoding="utf-8-sig"),
        "schema": json.loads((bench / "screen-schema.json").read_text(encoding="utf-8-sig")),
    }

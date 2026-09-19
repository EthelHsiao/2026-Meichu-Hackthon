"""main.py 的無狀態合約測試：monkeypatch call_ollama_generate，不需要真的 Ollama。
跑法：cd mi300-deploy/app && python -m pytest -q test_main.py
"""
import json

import main
from fastapi.testclient import TestClient

client = TestClient(main.app)


def test_health_reports_configured_models():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "text_model" in body and "vision_model" in body
    # 這幾個欄位是 feat/mi300-model-lab 的成果（2026-09-19 手動部署，這次補進 git），
    # 合併時故意保留，不要被回退掉。
    assert "vision_think" in body and "vision_keep_alive" in body and "app_sha256" in body


def test_screen_observations_returns_rich_schema(monkeypatch):
    calls = []

    async def fake_result(model, prompt, max_tokens=64, images=None, temperature=0.3, think=None, output_schema=None):
        calls.append((model, images is not None, output_schema is not None))
        return {
            "response": json.dumps({
                "app": "code", "activity": "在 main.py 除錯",
                "evidence": ["Traceback (most recent call last)", "KeyError: 'response'"],
                "error": {"kind": "runtime", "code": None, "message": "KeyError: 'response'",
                          "file": "main.py", "line": 12},
                "cause": None, "missing_context": [],
            }),
            "client_total_seconds": 0.01,
        }

    monkeypatch.setattr(main, "call_ollama_result", fake_result)
    resp = client.post(
        "/v1/screen-observations",
        json={"observation": {"observation_id": "o1"}, "image_b64": "anBlZw=="},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["app"] == "code"
    assert body["activity"] == "在 main.py 除錯"
    assert body["error"] == {"kind": "runtime", "code": None, "message": "KeyError: 'response'",
                              "file": "main.py", "line": 12}
    assert calls == [(main.VISION_MODEL, True, True)]


def test_screen_observations_falls_back_when_model_omits_json(monkeypatch):
    async def fake_result(model, prompt, max_tokens=64, images=None, temperature=0.3, think=None, output_schema=None):
        return {"response": "只是一段沒有 JSON 的文字", "client_total_seconds": 0.01}

    monkeypatch.setattr(main, "call_ollama_result", fake_result)
    resp = client.post(
        "/v1/screen-observations",
        json={"observation": {}, "image_b64": "anBlZw=="},
    )
    body = resp.json()
    assert body == {
        "app": None, "activity": None, "evidence": [], "error": None,
        "cause": None, "missing_context": [],
    }


def test_chat_completions_returns_openai_shaped_response(monkeypatch):
    async def fake_generate(model, prompt, max_tokens=64, images=None, temperature=0.3, think=None):
        return '{"expr": "worried", "text": "先印出 dict 看看？"}'

    monkeypatch.setattr(main, "call_ollama_generate", fake_generate)
    resp = client.post(
        "/v1/chat/completions",
        json={"messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "怎麼修"}]},
    )
    assert resp.status_code == 200
    content = json.loads(resp.json()["choices"][0]["message"]["content"])
    assert content == {"expr": "worried", "text": "先印出 dict 看看？"}


def test_chat_completions_falls_back_to_neutral_expr_on_bad_json(monkeypatch):
    async def fake_generate(model, prompt, max_tokens=64, images=None, temperature=0.3, think=None):
        return "沒有 JSON 的自由文字回覆"

    monkeypatch.setattr(main, "call_ollama_generate", fake_generate)
    resp = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "嗨"}]})
    content = json.loads(resp.json()["choices"][0]["message"]["content"])
    assert content["expr"] == "neutral"
    assert content["text"]


def test_chat_completions_repairs_unquoted_expr_value(monkeypatch):
    """實測抓到的真實案例：qwen2.5:7b-instruct 偶爾漏加引號，回
    {"expr": neutral, "text": "..."}，不應該整個退化成把原始文字塞進 text。"""
    async def fake_generate(model, prompt, max_tokens=64, images=None, temperature=0.3, think=None):
        return '{"expr": neutral, "text": "嗨，你好嗎？"}'

    monkeypatch.setattr(main, "call_ollama_generate", fake_generate)
    resp = client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hello"}]})
    content = json.loads(resp.json()["choices"][0]["message"]["content"])
    assert content == {"expr": "neutral", "text": "嗨，你好嗎？"}


def test_homework_analyses_returns_all_three_fields(monkeypatch):
    async def fake_generate(model, prompt, max_tokens=64, images=None, temperature=0.3, think=None):
        if images is not None:
            return "題目：1+1=? 使用者寫：2"
        return '{"expr": "happy", "text": "算對了，很棒！"}'

    monkeypatch.setattr(main, "call_ollama_generate", fake_generate)
    resp = client.post(
        "/v1/homework-analyses",
        json={"image_b64": "anBlZw==", "transcript": "這題我算了好久"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["analysis"] == "題目：1+1=? 使用者寫：2"
    assert body["reassurance"] == {"expr": "happy", "text": "算對了，很棒！"}
    assert "這題我算了好久" in body["chatgpt_prompt"]


# ---------------------------------------------------------------------------
# 模型評測工具（feat/mi300-model-lab 的成果）沒有被合併過程弄壞
# ---------------------------------------------------------------------------
def test_model_lab_endpoints_still_present():
    assert client.get("/model-lab").status_code == 200
    resp = client.get("/model-lab/defaults")
    assert resp.status_code == 200
    body = resp.json()
    assert "prompt" in body and "schema" in body


def test_analyze_screen_is_stateless_and_reports_json_validity(monkeypatch):
    async def fake_result(model, prompt, max_tokens=64, images=None, temperature=0.3, think=None, output_schema=None):
        return {"response": '{"app": "code"}', "client_total_seconds": 0.01}

    monkeypatch.setattr(main, "call_ollama_result", fake_result)
    resp = client.post("/analyze/screen", json={"image_b64": "anBlZw==", "prompt": "describe"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["json_valid"] is True
    assert body["parsed_json"] == {"app": "code"}

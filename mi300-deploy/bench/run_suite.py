"""Generate only synthetic fixtures and compare installed Ollama vision models."""
import argparse
import base64
import hashlib
import json
import statistics
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from jsonschema import Draft202012Validator

from benchmark import generate, request_json


CASES = [
    {
        "id": "typescript_compile", "app": "code", "kind": "compile", "code": "TS2322", "line": 8,
        "title": "main.ts - demo-project - Visual Studio Code",
        "file": "src/main.ts",
        "source": ["1  // Synthetic TypeScript example", "2", "3  export function run() {", "4    console.log('start');", "5  }", "6", "7  // count must be numeric", '8  const count: number = "five";'],
        "terminal": ["$ npm run build", "> tsc --noEmit", "src/main.ts(8,7): error TS2322: Type 'string' is not assignable to type 'number'.", "Found 1 error.", "Process exited with code 2."],
    },
    {
        "id": "python_runtime", "app": "code", "kind": "runtime", "code": "KeyError", "line": 12,
        "title": "client.py - demo-project - Visual Studio Code", "file": "client.py",
        "source": ["8  def main():", '9      payload = {"result": 42}', "10     print('processing response')", "11     # Read a response field", '12     print(payload["response"])', "13", '14 if __name__ == "__main__":', "15     main()"],
        "terminal": ["$ python client.py", "Traceback (most recent call last):", '  File "/workspace/client.py", line 15, in <module>', "    main()", '  File "/workspace/client.py", line 12, in main', '    print(payload["response"])', "KeyError: 'response'"],
    },
    {
        "id": "eslint", "app": "code", "kind": "lint", "code": "no-unused-vars", "line": 4,
        "title": "app.js - demo-project - Visual Studio Code", "file": "src/app.js",
        "source": ["1  export function main() {", "2    console.log('hello');", "3  }", "4  const unused = 42;"],
        "terminal": ["$ npm run lint", "> eslint src", "/workspace/src/app.js", "  4:7  error  'unused' is assigned a value but never used  no-unused-vars", "1 problem (1 error, 0 warnings)"],
    },
    {
        "id": "test_failure", "app": "code", "kind": "test", "code": "AssertionError", "line": 5,
        "title": "test_math.py - demo-project - Visual Studio Code", "file": "tests/test_math.py",
        "source": ["1  from calculator import add", "2", "3  def test_add():", "4      actual = add(2, 2)", "5      assert actual == 4", "", "# calculator.py is not shown."],
        "terminal": ["$ pytest -q", "FAILED tests/test_math.py::test_add", "    def test_add():", "        actual = add(2, 2)", ">       assert actual == 4", "E       AssertionError: assert 5 == 4", "tests/test_math.py:5: AssertionError", "1 failed in 0.03s"],
    },
    {
        "id": "clean_editor", "app": "code", "kind": None, "code": None, "line": None,
        "title": "main.ts - demo-project - Visual Studio Code", "file": "src/main.ts",
        "source": ["1  export function greet(name: string): string {", "2    return 'Hello ' + name;", "3  }", "4", "5  console.log(greet('Ada'));"],
        "terminal": ["$ npm run build", "> tsc --noEmit", "Build completed successfully.", "Process exited with code 0.", "$"],
    },
    {
        "id": "documentation_not_error", "app": "chrome", "kind": None, "code": None, "line": None,
        "title": "Python exception reference - Google Chrome", "file": "docs.example.test/python/exceptions",
        "source": ["Python exception reference", "", "KeyError", "Raised when a mapping key is not found in a dictionary.", "", "Example message: KeyError: 'response'", "", "This page is documentation, not output from a running program."],
        "terminal": None,
    },
]


def fixtures(root):
    root.mkdir(parents=True, exist_ok=True)
    font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")
    if not font_path.exists():
        raise RuntimeError("Install fonts-dejavu-core to render readable synthetic fixtures")
    font = ImageFont.truetype(str(font_path), 22)
    title_font = ImageFont.truetype(str(font_path), 24)
    paths = {}
    for case in CASES:
        image = Image.new("RGB", (1920, 1080), "#1e1e1e")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 1920, 52), fill="#383838")
        draw.text((22, 12), case["title"], font=title_font, fill="white")
        draw.text((22, 66), "SYNTHETIC EVALUATION FIXTURE - NO USER DATA", font=font, fill="#75bfff")
        draw.rectangle((0, 115, 280, 1040), fill="#252526")
        draw.text((20, 138), "EXPLORER" if case["terminal"] else "REFERENCE", font=font, fill="#cccccc")
        draw.text((20, 185), "demo-project", font=font, fill="#cccccc")
        draw.text((308, 126), case["file"], font=font, fill="#75bfff")
        for index, line in enumerate(case["source"]):
            draw.text((308, 184 + index * 34), line, font=font, fill="#e6e6e6")
        if case["terminal"]:
            draw.rectangle((281, 620, 1919, 1040), fill="#181818")
            draw.text((306, 632), "PROBLEMS    OUTPUT    DEBUG CONSOLE    TERMINAL", font=font, fill="#bbbbbb")
            for index, line in enumerate(case["terminal"]):
                color = "#f5a5a5" if "Error" in line or "error" in line or "FAILED" in line else "#eeeeee"
                draw.text((306, 685 + index * 36), line, font=font, fill=color)
        draw.rectangle((0, 1040, 1920, 1080), fill="#007acc")
        draw.text((20, 1046), "demo-project     UTF-8", font=font, fill="white")
        path = root / (case["id"] + ".png")
        image.save(path)
        paths[case["id"]] = path
    return paths


def check(case, result, validator):
    data = result.get("parsed_json")
    schema_errors = [error.message for error in validator.iter_errors(data)]
    if schema_errors:
        return {"schema_valid": False, "schema_errors": schema_errors, "checks": {}}
    error = data["error"]
    checks = {"app": case["app"] in (data["app"] or "").lower()}
    if case["kind"] is None:
        checks["no_false_error"] = error is None
    else:
        checks["kind"] = isinstance(error, dict) and error["kind"] == case["kind"]
        checks["code_or_exception"] = isinstance(error, dict) and case["code"].lower() in ((error["code"] or "") + " " + (error["message"] or "")).lower()
        checks["line"] = isinstance(error, dict) and error["line"] == case["line"]
    return {"schema_valid": True, "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--think", choices=["auto", "off"], default="off")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.root
    paths = fixtures(root / "synthetic-fixtures")
    schema = json.loads((root / "screen-schema.json").read_text(encoding="utf-8-sig"))
    validator = Draft202012Validator(schema)
    prompt = (root / "screen-prompt.txt").read_text(encoding="utf-8-sig")
    prompt += "\nerror.code includes compiler codes, lint rules, or exception class names when visible."
    base = {"model": args.model, "prompt": prompt, "format": schema, "stream": True,
            "keep_alive": "10m", "options": {"num_ctx": 8192, "num_predict": 768, "temperature": 0, "seed": 42}}
    if args.think == "off":
        base["think"] = False
    report_path = root / (args.label + ".results.jsonl")
    rows = []
    with report_path.open("x", encoding="utf-8") as output:
        output.write(json.dumps({"kind": "metadata", "model": args.model, "prompt": prompt, "schema": schema,
                                 "options": base["options"], "think": args.think,
                                 "version": request_json("http://localhost:11434/api/version"),
                                 "tags": request_json("http://localhost:11434/api/tags"),
                                 "note": "Synthetic fixtures, one warmup, six distinct cases then two cached repeats; not a real screenshot benchmark."}, ensure_ascii=False) + "\n")
        plan = [("warmup", CASES[0])] + [("distinct", case) for case in CASES] + [("repeat", CASES[0])] * 2
        for phase, case in plan:
            raw = paths[case["id"]].read_bytes()
            payload = {**base, "images": [base64.b64encode(raw).decode()]}
            try:
                result = generate("http://localhost:11434", payload, 600)
                row = {"phase": phase, "case": case["id"], "image_sha256": hashlib.sha256(raw).hexdigest(),
                       **result, **check(case, result, validator)}
            except Exception as exc:
                detail = exc.read().decode(errors="replace") if hasattr(exc, "read") else str(exc)
                row = {"phase": phase, "case": case["id"], "error": detail}
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            output.flush()
            print(json.dumps(row, ensure_ascii=False), flush=True)
            rows.append(row)
            if "error" in row:
                break
    distinct = [row for row in rows if row["phase"] == "distinct" and "error" not in row]
    checks = [value for row in distinct for value in row.get("checks", {}).values()]
    summary = {"model": args.model, "distinct_cases": len(distinct),
               "schema_valid": sum(row["schema_valid"] for row in distinct),
               "field_checks_pass": sum(checks), "field_checks_total": len(checks),
               "distinct_wall_median_s": statistics.median([row["wall_s"] for row in distinct]) if distinct else None,
               "distinct_wall_max_s": max([row["wall_s"] for row in distinct]) if distinct else None,
               "errors": [row for row in rows if "error" in row],
               "results": str(report_path),
               "note": "Small synthetic smoke test; root cause and evidence require manual review."}
    (root / (args.label + ".summary.json")).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

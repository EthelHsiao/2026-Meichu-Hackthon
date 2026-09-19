"""Prompt + optional image benchmark for Ollama; Python 3.10+, no dependencies."""
import argparse
import base64
import hashlib
import json
import math
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request_json(url, payload=None, timeout=300):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def generate(url, payload, timeout):
    body = json.dumps(payload).encode("utf-8")
    request = Request(url + "/api/generate", data=body,
                      headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    first_content = first_output = None
    content, thinking = [], []
    final = None
    with urlopen(request, timeout=timeout) as response:
        for line in response:
            if not line.strip():
                continue
            chunk = json.loads(line)
            elapsed = time.perf_counter() - start
            if chunk.get("error"):
                raise RuntimeError(chunk["error"])
            answer, thought = chunk.get("response", ""), chunk.get("thinking", "")
            if (answer or thought) and first_output is None:
                first_output = elapsed
            if answer and first_content is None:
                first_content = elapsed
            content.append(answer)
            thinking.append(thought)
            if chunk.get("done"):
                final = chunk
                break
    total = time.perf_counter() - start
    if final is None:
        raise RuntimeError("Stream ended without a done record; incomplete response")
    answer = "".join(content)
    try:
        parsed = json.loads(answer)
        json_valid = True
    except ValueError:
        parsed, json_valid = None, False
    durations = {key + "_s": final[key] / 1e9 for key in (
        "total_duration", "load_duration", "prompt_eval_duration", "eval_duration"
    ) if key in final}
    eval_time = durations.get("eval_duration_s", 0)
    return {
        "ttft_output_s": first_output,
        "ttft_content_s": first_content,
        "wall_s": total,
        **durations,
        "prompt_eval_count": final.get("prompt_eval_count"),
        "prompt_eval_cached_count": final.get("prompt_eval_cached_count"),
        "eval_count": final.get("eval_count"),
        "decode_tokens_per_s": final.get("eval_count", 0) / eval_time if eval_time else None,
        "done_reason": final.get("done_reason"),
        "json_valid": json_valid,
        "parsed_json": parsed,
        "response": answer,
        "thinking": "".join(thinking),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:11435")
    parser.add_argument("--model", required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt")
    source.add_argument("--prompt-file", type=Path)
    parser.add_argument("--image", type=Path, action="append", default=[],
                        help="Repeat for full screenshot plus crop; bytes are sent unchanged")
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--context", type=int, default=8192)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--think", choices=["auto", "off", "on"], default="auto")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output", type=Path, required=True,
                        help="New JSONL file; existing files are never overwritten")
    args = parser.parse_args()
    if min(args.runs, args.context, args.max_tokens, args.timeout) <= 0 or args.warmup < 0:
        parser.error("runs/context/max-tokens/timeout must be positive; warmup >= 0")
    url = args.url.rstrip("/")
    prompt = args.prompt_file.read_text(encoding="utf-8-sig") if args.prompt_file else args.prompt
    schema = json.loads(args.schema.read_text(encoding="utf-8-sig")) if args.schema else None
    images, image_info = [], []
    for path in args.image:
        raw = path.read_bytes()
        images.append(base64.b64encode(raw).decode("ascii"))
        image_info.append({"path": str(path), "bytes": len(raw),
                           "sha256": hashlib.sha256(raw).hexdigest()})
    payload = {
        "model": args.model, "prompt": prompt, "stream": True, "keep_alive": "10m",
        "options": {"temperature": args.temperature, "seed": args.seed,
                    "num_ctx": args.context, "num_predict": args.max_tokens},
    }
    if images:
        payload["images"] = images
    if schema is not None:
        payload["format"] = schema
    if args.think != "auto":
        payload["think"] = args.think == "on"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    measured = []
    with args.output.open("x", encoding="utf-8") as output:
        version = request_json(url + "/api/version", timeout=args.timeout)
        tags = request_json(url + "/api/tags", timeout=args.timeout)
        metadata = {"kind": "metadata", "time_utc": datetime.now(timezone.utc).isoformat(),
                    "url": url, "ollama": version, "installed_models": tags,
                    "model": args.model, "prompt": prompt, "schema": schema,
                    "images": image_info, "options": payload["options"],
                    "think": args.think, "keep_alive": payload["keep_alive"],
                    "warmup": args.warmup, "runs": args.runs,
                    "note": "Repeated identical input may reuse caches. JSON validity is syntax only."}
        output.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        output.flush()
        for index in range(args.warmup + args.runs):
            phase = "warmup" if index < args.warmup else "measured"
            try:
                result = generate(url, payload, args.timeout)
            except (HTTPError, URLError, OSError, ValueError, RuntimeError) as exc:
                detail = exc.read().decode("utf-8", errors="replace") if isinstance(exc, HTTPError) else str(exc)
                output.write(json.dumps({"kind": "error", "phase": phase, "error": detail}) + "\n")
                raise RuntimeError(detail) from exc
            record = {"kind": "run", "phase": phase, "index": index, **result}
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            print(json.dumps(record, ensure_ascii=False, indent=2), flush=True)
            if phase == "measured":
                measured.append(result)
        summary = {"kind": "summary", "runs": len(measured),
                   "json_valid_runs": sum(row["json_valid"] for row in measured),
                   "truncated_runs": sum(row["done_reason"] == "length" for row in measured)}
        for metric in ("wall_s", "ttft_content_s", "ttft_output_s"):
            values = sorted(row[metric] for row in measured if row[metric] is not None)
            summary[metric] = ({"p50": statistics.median(values),
                                "p95_nearest_rank": values[math.ceil(.95 * len(values)) - 1]}
                               if values else None)
        output.write(json.dumps(summary, ensure_ascii=False) + "\n")
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        sys.exit(1)

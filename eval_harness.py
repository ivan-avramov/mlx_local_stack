#!/usr/bin/env python3
"""
eval_harness.py — model evaluation harness for the mlx_local_stack.

Drives the mlx-serve router (OpenAI-compatible, :8000) over HTTP ONLY. No in-process
MLX. The router auto-instantiates each model on first request (on_demand) and keeps
exactly one model resident, so every run is model-outer / task-inner: preload a model,
run all its work, then move on (one swap per model, never per task).

Speed numbers come from the router's own telemetry: stream every request so the router
records ttft_ms, then read the newest row from /v1/metrics/requests (also persisted to
requests.jsonl). Decode tok/s is authoritative; prefill tok/s is DERIVED as
prompt_tokens / (ttft_ms/1000) and labelled as such.

Stdlib only — run with:  uv run --with - python eval_harness.py ...   (no deps needed
for speed/needle; the `tasks` judge uses the Anthropic HTTP API via urllib + ANTHROPIC_API_KEY).

Usage:
  python eval_harness.py speed  [--models A,B] [--depths 2000,16000,64000] [--gen 256]
  python eval_harness.py needle [--models A,B] [--depths 16000,64000,128000]
  python eval_harness.py tasks  [--models A,B] [--judge claude-sonnet-4-6]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get("MLX_SERVE_BASE", "http://localhost:8000")
RESULTS_DIR = Path(os.environ.get("EVAL_RESULTS_DIR", "eval_results"))
# Subject codebases (the mlx-vlm fork is the primary subject; siblings pad to 256K with
# DISTINCT real source rather than repeated content).
SUBJECT_GLOBS = [
    "src/mlx-vlm/mlx_vlm/**/*.py",
    "src/mlx-serve/src/mlx_serve/**/*.py",
]
DEFAULT_DEPTHS = [2000, 16000, 64000]
CHARS_PER_TOKEN = 3.6  # rough; the recorded prompt_tokens is the source of truth


# --------------------------------------------------------------------------- HTTP
def _post(path: str, payload: dict, timeout: float = 3600) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _get(path: str, timeout: float = 60) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def models_from_router() -> list[str]:
    """Self-correcting roster: whatever the live config serves."""
    return [m["id"] for m in _get("/v1/models")["data"]]


def status() -> dict:
    return _get("/v1/status")


def preload(model: str, timeout: float = 900) -> dict:
    t0 = time.perf_counter()
    r = _post("/v1/models/load", {"model": model, "keep_alive": "180m"}, timeout=timeout)
    return {"status": r.get("status"), "load_s": round(time.perf_counter() - t0, 2)}


def last_metric(model: str) -> dict:
    rows = _get(f"/v1/metrics/requests?model={model}&last_n=1")["requests"]
    return rows[0] if rows else {}


def probe(model: str, messages: list, max_tokens: int = 256,
          temperature: float = 0.0, timeout: float = 3600) -> dict:
    """Non-streaming request. Returns the upstream `timings` (clean decode tok/s + peak_memory),
    `usage`, the assistant message, and client wall-clock. Prefill tok/s is derived from
    (wall - decode_time) since mlx_vlm reports prompt_ms=0."""
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens,
               "temperature": temperature, "stream": False}
    t0 = time.perf_counter()
    r = _post("/v1/chat/completions", payload, timeout=timeout)
    wall = time.perf_counter() - t0
    tm = r.get("timings") or {}
    us = r.get("usage") or {}
    msg = (r.get("choices") or [{}])[0].get("message", {})
    pn = us.get("prompt_tokens") or tm.get("prompt_n")
    pred_ms = tm.get("predicted_ms") or 0.0
    prefill_s = wall - pred_ms / 1000.0
    prefill_tps = round(pn / prefill_s, 1) if (pn and prefill_s > 0.3) else None
    return {
        "content": msg.get("content") or "", "reasoning": msg.get("reasoning") or "",
        "prompt_tokens": pn, "completion_tokens": us.get("completion_tokens"),
        "decode_tps": tm.get("predicted_per_second"), "prefill_tps_derived": prefill_tps,
        "predicted_ms": round(pred_ms, 1), "peak_mem_gb": tm.get("peak_memory"),
        "wall_s": round(wall, 1),
    }


def stream_chat(model: str, messages: list, max_tokens: int = 256,
                temperature: float = 0.0, timeout: float = 3600) -> dict:
    """Stream a completion (so the router records ttft_ms). Returns assembled text + client timing."""
    payload = {
        "model": model, "messages": messages, "max_tokens": max_tokens,
        "temperature": temperature, "stream": True,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + "/v1/chat/completions", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    chunks: list[str] = []
    t0 = time.perf_counter()
    first = None
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            body = line[len("data:"):].strip()
            if body == "[DONE]":
                break
            try:
                obj = json.loads(body)
            except json.JSONDecodeError:
                continue
            delta = (obj.get("choices") or [{}])[0].get("delta", {})
            tok = delta.get("content")
            if tok:
                if first is None:
                    first = time.perf_counter()
                chunks.append(tok)
    return {
        "text": "".join(chunks),
        "client_ttft_s": round(first - t0, 3) if first else None,
        "client_total_s": round(time.perf_counter() - t0, 3),
    }


# --------------------------------------------------------------------------- context
_CORPUS_CACHE: str | None = None


def corpus() -> str:
    global _CORPUS_CACHE
    if _CORPUS_CACHE is not None:
        return _CORPUS_CACHE
    parts = []
    for g in SUBJECT_GLOBS:
        for f in sorted(glob.glob(g, recursive=True)):
            try:
                parts.append(f"# FILE: {f}\n" + Path(f).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    _CORPUS_CACHE = "\n\n".join(parts)
    return _CORPUS_CACHE


def make_context(target_tokens: int) -> str:
    base = corpus()
    chars = int(target_tokens * CHARS_PER_TOKEN)
    if len(base) >= chars:
        return base[:chars]
    # distinct content exhausted — return all of it (true size recorded from metrics)
    return base


def strip_thinking(text: str) -> str:
    """Remove <think>...</think> reasoning traces before judging answer quality."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# --------------------------------------------------------------------------- results io
def _writer(name: str):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / name
    f = path.open("a", encoding="utf-8")

    def write(row: dict):
        f.write(json.dumps(row) + "\n")
        f.flush()

    return write, path


def _select_models(arg: str | None) -> list[str]:
    live = models_from_router()
    if not arg:
        return live
    want = [m.strip() for m in arg.split(",") if m.strip()]
    bad = [m for m in want if m not in live]
    if bad:
        sys.exit(f"unknown models (not served): {bad}\nserved: {live}")
    return want


# --------------------------------------------------------------------------- stage 0a: speed
def cmd_speed(args):
    depths = [int(x) for x in args.depths.split(",")]
    models = _select_models(args.models)
    write, path = _writer("stage0_speed.jsonl")
    print(f"[speed] {len(models)} models x {len(depths)} depths -> {path}", flush=True)
    for model in models:
        print(f"\n=== {model} ===", flush=True)
        try:
            pre = preload(model)
        except Exception as e:  # noqa: BLE001
            print(f"  preload FAILED: {e}", flush=True)
            write({"model": model, "phase": "preload", "error": str(e)})
            continue
        st = status().get("memory", {})
        print(f"  loaded in {pre['load_s']}s | sys used={st.get('used_gb')}GB avail={st.get('available_gb')}GB", flush=True)
        for depth in depths:
            ctx = make_context(depth)
            msgs = [
                {"role": "system", "content": "You are a senior engineer reading source code."},
                {"role": "user", "content": ctx + "\n\n---\nIn ~120 words, summarize what this code does."},
            ]
            try:
                p = probe(model, msgs, max_tokens=args.gen)
                row = {"model": model, "phase": "speed", "depth_nominal": depth,
                       "load_s": pre["load_s"], "sys_used_gb": st.get("used_gb"), **p}
                write(row)
                print(f"  depth~{depth:>7} | prompt_tok={p['prompt_tokens']} | "
                      f"prefill~{p['prefill_tps_derived']} tok/s | decode={p['decode_tps']} tok/s | "
                      f"peak={p['peak_mem_gb']}GB | wall={p['wall_s']}s", flush=True)
            except Exception as e:  # noqa: BLE001 — OOM / ceiling
                write({"model": model, "phase": "speed", "depth_nominal": depth, "error": str(e)})
                print(f"  depth~{depth} FAILED ({e}) -> treating as context ceiling, next model", flush=True)
                break
    print(f"\n[speed] done -> {path}", flush=True)


# --------------------------------------------------------------------------- stage 0b: needle
NEEDLES = [
    ("the secret build code is ZEPHYR-{n}", "What is the secret build code?", "ZEPHYR-{n}"),
]


def cmd_needle(args):
    depths = [int(x) for x in args.depths.split(",")]
    positions = [float(x) for x in args.positions.split(",")]
    models = _select_models(args.models)
    write, path = _writer("stage0_needle.jsonl")
    print(f"[needle] {len(models)} models x {len(depths)} depths x {len(positions)} positions -> {path}", flush=True)
    for model in models:
        print(f"\n=== {model} ===", flush=True)
        try:
            preload(model)
        except Exception as e:  # noqa: BLE001
            write({"model": model, "phase": "needle", "error": str(e)})
            continue
        for depth in depths:
            base = make_context(depth)
            for pos in positions:
                tag = f"{int(depth)}-{pos}"
                fact = NEEDLES[0][0].format(n=tag)
                q = NEEDLES[0][1]
                gold = NEEDLES[0][2].format(n=tag)
                cut = int(len(base) * pos)
                ctx = base[:cut] + f"\n\nNOTE: {fact}.\n\n" + base[cut:]
                msgs = [
                    {"role": "system", "content": "Answer using only the provided text."},
                    {"role": "user", "content": ctx + f"\n\n---\n{q} Answer with the code only."},
                ]
                try:
                    # thinking eats budget; give headroom so a real answer survives the trace
                    p = probe(model, msgs, max_tokens=args.gen)
                    ans = strip_thinking(p["content"])
                    ok = gold.lower() in ans.lower()
                    write({"model": model, "phase": "needle", "depth_nominal": depth,
                           "position": pos, "gold": gold, "answer": ans[:120], "hit": ok,
                           "prompt_tokens": p["prompt_tokens"], "decode_tps": p["decode_tps"]})
                    print(f"  depth~{depth:>7} pos={pos} | {'HIT ' if ok else 'MISS'} | got={ans[:40]!r}", flush=True)
                except Exception as e:  # noqa: BLE001
                    write({"model": model, "phase": "needle", "depth_nominal": depth,
                           "position": pos, "error": str(e)})
                    print(f"  depth~{depth} pos={pos} FAILED ({e})", flush=True)
                    break
    print(f"\n[needle] done -> {path}", flush=True)


# --------------------------------------------------------------------------- stage 1: tasks (scaffold)
def cmd_tasks(args):
    print("Stage 1 (reasoning+coding, LLM-judged) is scaffolded but needs the task set and "
          "ground-truth wired in. Run `speed` and `needle` first to prune the roster, then "
          "we promote survivors here.", flush=True)


# --------------------------------------------------------------------------- main
def main():
    p = argparse.ArgumentParser(description="mlx_local_stack model eval harness (pure HTTP)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("speed", help="Stage 0a: load time, prefill/decode tok/s, TTFT by depth")
    s.add_argument("--models", default=None, help="comma list; default = all served")
    s.add_argument("--depths", default=",".join(str(d) for d in DEFAULT_DEPTHS))
    s.add_argument("--gen", type=int, default=256, help="max generated tokens per probe")
    s.set_defaults(func=cmd_speed)

    n = sub.add_parser("needle", help="Stage 0b: needle-in-haystack retrieval by depth x position")
    n.add_argument("--models", default=None)
    n.add_argument("--depths", default="16000,64000,128000")
    n.add_argument("--positions", default="0.1,0.5,0.9")
    n.add_argument("--gen", type=int, default=768, help="max tokens; needs headroom past the thinking trace")
    n.set_defaults(func=cmd_needle)

    t = sub.add_parser("tasks", help="Stage 1: reasoning+coding (LLM-judged) [scaffold]")
    t.add_argument("--models", default=None)
    t.add_argument("--judge", default="claude-sonnet-4-6")
    t.set_defaults(func=cmd_tasks)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

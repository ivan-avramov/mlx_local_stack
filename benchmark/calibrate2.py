#!/usr/bin/env python3
"""Focused calibration: does temp 0.0 cause thinking-loops (hit the cap, no answer)?
Does a thinking_budget knob work? Real AIME item, so we also sanity-check correctness
and validate the harness end-to-end. Pure HTTP."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import benchmarks, client, extract

item = benchmarks.load("aime", limit=1, seed=0)[0]
msgs = benchmarks.build_messages("aime", item)
gold = item["answer"]
print(f"AIME item {item['id']} gold={gold}\n")

# (label, model, temperature, max_tokens, extra_body)
CONFIGS = [
    ("MoE temp0.6",        "gemma-4-26B-A4B-it-QAT-MLX-4bit", 0.6, 8192, {}),
    ("MoE temp0.0",        "gemma-4-26B-A4B-it-QAT-MLX-4bit", 0.0, 8192, {}),
    ("MoE budget1024",     "gemma-4-26B-A4B-it-QAT-MLX-4bit", 0.0, 8192, {"thinking_budget": 1024}),
    ("dense temp0.6",      "gemma-4-31b-it-UD-MLX-4bit",      0.6, 8192, {}),
]

cur = None
for label, model, temp, mx, extra in CONFIGS:
    if model != cur:
        client.preload(model); cur = model
    body = {"model": model, "messages": msgs, "max_tokens": mx,
            "temperature": temp, "stream": False, **extra}
    t0 = time.perf_counter()
    try:
        r = client._post("/v1/chat/completions", body, timeout=1700)
        wall = time.perf_counter() - t0
        tm = r.get("timings") or {}; us = r.get("usage") or {}
        msg = (r.get("choices") or [{}])[0].get("message", {})
        fr = (r.get("choices") or [{}])[0].get("finish_reason")
        ans = extract.extract_int(client.strip_thinking(msg.get("content") or ""))
        print(f"{label:<16} | comp_tok={us.get('completion_tokens')} | finish={fr} | "
              f"wall={wall:.0f}s | decode={tm.get('predicted_per_second'):.1f} | "
              f"answer={ans} ({'CORRECT' if str(ans)==str(gold) else 'wrong'}) | "
              f"reasoning_chars={len(msg.get('reasoning') or '')}", flush=True)
    except Exception as e:
        print(f"{label:<16} | FAILED: {type(e).__name__}: {str(e)[:90]}", flush=True)
print("\n[calibrate2] done")

#!/usr/bin/env python3
"""Incremental long-context memory probe. Ramps context in fixed increments (default 8K)
and records the memory situation at each step until OOM or the target — more realistic than
a single 256K dump, and it maps the peak-mem-vs-context curve + finds the true ceiling per
model. Pure HTTP, strictly sequential (one model, one request at a time — nothing else should
hit the stack while this runs).

Note: timings.peak_memory is a process high-water mark (can't be reset over HTTP), but since
we ramp UP monotonically it tracks the per-step peak correctly. We also record system used_gb
from /v1/status as the current footprint at each step.
"""
import argparse
import glob
import json
import time
import urllib.request
from pathlib import Path

BASE = "http://localhost:8000"


def post(path, payload, timeout=3600):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def get(path, timeout=30):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read())


def corpus():
    parts = []
    for g in ["src/mlx-vlm/mlx_vlm/**/*.py", "src/mlx-serve/src/mlx_serve/**/*.py"]:
        for f in sorted(glob.glob(g, recursive=True)):
            try:
                parts.append(Path(f).read_text(errors="replace"))
            except OSError:
                pass
    return "\n\n".join(parts) or "filler text. "


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gemma-4-26b-a4b-it-8bit,Qwen3.6-27B-UD-MLX-6bit")
    ap.add_argument("--step", type=int, default=8000, help="context increment in tokens")
    ap.add_argument("--max", type=int, default=256000, help="max context to attempt")
    ap.add_argument("--out", default="eval_results/ctx_memory_curve.jsonl")
    a = ap.parse_args()
    base = corpus()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    fout = open(a.out, "a", encoding="utf-8")
    print(f"[ctx_curve] step={a.step} max={a.max} models={a.models}", flush=True)

    for m in [x.strip() for x in a.models.split(",")]:
        print(f"\n=== {m} ===", flush=True)
        post("/v1/models/load", {"model": m, "keep_alive": "60m"}, timeout=900)
        cal = post("/v1/chat/completions", {"model": m, "messages": [{"role": "user", "content": base[:40000]}],
                                            "max_tokens": 1, "temperature": 0.0, "stream": False}, timeout=600)
        cpt = 40000 / ((cal.get("usage") or {}).get("prompt_tokens") or (cal.get("timings") or {}).get("prompt_n"))
        print(f"  {cpt:.2f} chars/token", flush=True)
        for target in range(a.step, a.max + 1, a.step):
            chars = int(target * cpt)
            ctx = (base * (chars // len(base) + 1))[:chars]
            try:
                t0 = time.perf_counter()
                r = post("/v1/chat/completions", {"model": m, "messages": [{"role": "user", "content": ctx + "\n\nReply: OK."}],
                                                  "max_tokens": 8, "temperature": 0.0, "stream": False}, timeout=3600)
                wall = time.perf_counter() - t0
                tm = r.get("timings") or {}
                us = r.get("usage") or {}
                pt = us.get("prompt_tokens") or tm.get("prompt_n")
                pred_ms = tm.get("predicted_ms") or 0.0
                prefill_s = max(wall - pred_ms / 1000, 0.01)
                sys_used = (get("/v1/status").get("memory") or {}).get("used_gb")
                row = {"model": m, "target_tokens": target, "prompt_tokens": pt,
                       "peak_mem_gb": tm.get("peak_memory"), "sys_used_gb": sys_used,
                       "prefill_tps": round(pt / prefill_s), "decode_tps": tm.get("predicted_per_second")}
                fout.write(json.dumps(row) + "\n")
                fout.flush()
                print(f"  ctx~{target:>7} | prompt_tok={pt} | peak={tm.get('peak_memory')}GB | "
                      f"sys_used={sys_used}GB | prefill~{row['prefill_tps']} tok/s", flush=True)
            except Exception as e:  # noqa: BLE001
                fout.write(json.dumps({"model": m, "target_tokens": target, "error": str(e)[:140]}) + "\n")
                fout.flush()
                print(f"  ctx~{target} | OOM/ERROR -> ceiling for {m} ({str(e)[:60]})", flush=True)
                break
    print("\n[ctx_curve] done", flush=True)


if __name__ == "__main__":
    main()

"""
Decode-rate bench — measures decode tok/s for NOVEL generation (no context to
quote: the 'livelier UI' regime where suffix decoding can't help) vs a
CONTEXT-QUOTING prompt (where suffix excels). Run against the server with
suffix on, then relaunch with suffix off, and compare.

  PYTHONPATH=src/mlx-vlm .venv/bin/python benchmark/spikes/decode_bench.py [--model M]
"""
import argparse
import json
import time
import urllib.request

BASE = "http://localhost:8000"

NOVEL = (
    "Write an original, detailed 400-word essay on the cultural history of tea "
    "across China, Japan, and Britain. Use varied prose; do not repeat the prompt."
)
# A ~300-word passage the model must reproduce verbatim -> high suffix acceptance.
_PASSAGE = (
    "The lighthouse keeper rose before dawn, as he had for thirty years. " * 40
)
QUOTE = f"Here is a passage:\n\n{_PASSAGE}\n\nReproduce the passage above exactly, verbatim, with no commentary."


def gen(model, prompt, max_tokens=400):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(BASE + "/v1/chat/completions", body,
                                {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    r = json.load(urllib.request.urlopen(req, timeout=900))
    wall = time.perf_counter() - t0
    usage = r.get("usage", {}) or {}
    ct = usage.get("completion_tokens", 0)
    timings = r.get("timings", {}) or {}
    dps = timings.get("predicted_per_second")
    derived = ct / wall if wall > 0 else 0
    return ct, wall, dps, derived


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="unsloth/Qwen3.6-27B-UD-MLX-6bit")
    ap.add_argument("--max-tokens", type=int, default=400)
    args = ap.parse_args()
    print(f"model={args.model}  max_tokens={args.max_tokens}")
    for name, prompt in [("NOVEL (UI-like)", NOVEL), ("QUOTE (suffix-friendly)", QUOTE)]:
        ct, wall, dps, derived = gen(args.model, prompt, args.max_tokens)
        dps_s = f"{dps:.2f}" if dps else "n/a"
        print(f"  {name:24s}: completion={ct:4d} tok  wall={wall:6.1f}s  "
              f"decode={dps_s} tok/s (server)  {derived:.2f} tok/s (derived)")
    print("DONE")

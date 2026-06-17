#!/usr/bin/env python3
"""Measure drafter-free SuffixDecoding on the real Qwen3.6-27B (GatedDeltaNet).

Drives the running mlx-serve router (:8000) over HTTP. Suffix decoding is enabled
at model load (main_models.yaml), so a true with/without A/B would need a reload;
instead we use the echo-vs-novel contrast on the suffix-enabled model: only
ACCEPTED speculation can push decode tok/s above the model's intrinsic per-forward
rate, so echo >> novel demonstrates suffix is accepting drafts. The echo output
also validates correctness on the turboquant-KV + GDN path.

Thinking is capped via the `thinking_budget` body param (Qwen ignores /no_think),
so the echoed answer — not a long novel reasoning trace — dominates decode tok/s.

Run (stack must be up):  uv run --project .. python benchmark/suffix_qwen_ab.py
Loads one model and unloads it at the end (RAM hygiene on this laptop).
"""
import argparse
import json
import time
import urllib.request

BASE = "http://localhost:8000"
MODEL = "Qwen3.6-27B-UD-MLX-6bit"

# ~25-line block; "repeat N times" makes the answer almost pure echo (copy 1 echoes
# the prompt, copies 2..N echo prior output) -> high suffix acceptance throughout.
CODE = '''def fib(n):
    """Return the n-th Fibonacci number."""
    if n < 2:
        return n
    a, b = 0, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return b


def is_prime(n):
    if n < 2:
        return False
    for d in range(2, int(n ** 0.5) + 1):
        if n % d == 0:
            return False
    return True


def quicksort(xs):
    if len(xs) <= 1:
        return xs
    pivot = xs[len(xs) // 2]
    lo = [x for x in xs if x < pivot]
    mid = [x for x in xs if x == pivot]
    hi = [x for x in xs if x > pivot]
    return quicksort(lo) + mid + quicksort(hi)'''


def _post(path, payload, timeout=3600):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def run(label, messages, max_tokens, thinking_budget):
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_tokens,
               "temperature": 0.0, "stream": False, "thinking_budget": thinking_budget}
    t0 = time.perf_counter()
    r = _post("/v1/chat/completions", payload)
    wall = time.perf_counter() - t0
    tm, us = r.get("timings") or {}, r.get("usage") or {}
    msg = (r.get("choices") or [{}])[0].get("message", {})
    body, think = msg.get("content") or "", msg.get("reasoning") or ""
    print(f"\n=== {label} ===")
    print(f"  decode_tps={tm.get('predicted_per_second'):.2f} "
          f"completion_tok={us.get('completion_tokens')} thinking_chars={len(think)} "
          f"wall={wall:.1f}s peak={tm.get('peak_memory')}GB")
    print("  out[:200]:", body[:200].replace("\n", "⏎ "))
    return tm.get("predicted_per_second")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-tokens", type=int, default=600)
    ap.add_argument("--thinking-budget", type=int, default=4, help="cap thinking tokens")
    ap.add_argument("--keep", action="store_true", help="don't unload model at end")
    args = ap.parse_args()

    print(f"loading {MODEL} ...")
    print(" ", _post("/v1/models/load", {"model": MODEL, "keep_alive": "30m"}, timeout=900))

    echo = [
        {"role": "system", "content": "You are a code formatter. Output only code."},
        {"role": "user", "content": "Repeat the following Python code EXACTLY FOUR times, "
         "each copy separated by a line containing only '# ---':\n\n" + CODE},
    ]
    novel = [
        {"role": "system", "content": "You are a creative writer."},
        {"role": "user", "content": "Write an original ~400-word reflection on how rivers "
         "shape the land over time. Vary your wording; never repeat a phrase or sentence."},
    ]

    try:
        e = run("echo ", echo, args.max_tokens, args.thinking_budget)
        n = run("novel", novel, args.max_tokens, args.thinking_budget)
        if e and n:
            print(f"\n>>> decode tok/s: echo={e:.2f}  novel(baseline)={n:.2f}  "
                  f"speedup={e / n:.2f}x")
            print(">>> >1x = suffix decoding accepted drafts on echo-heavy output.")
    finally:
        if not args.keep:
            print("\nunloading", MODEL, "...")
            print(" ", _post("/v1/models/unload", {"model": MODEL}, timeout=60))


if __name__ == "__main__":
    main()

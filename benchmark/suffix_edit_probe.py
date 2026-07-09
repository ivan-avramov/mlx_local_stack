#!/usr/bin/env python3
"""Suffix-decode speed probe (Phase-2 #4).

Times decode tok/s for one or more served models on a chosen workload, to
characterize drafter-free n-gram / prompt-lookup (suffix) decoding:

    python suffix_edit_probe.py <model1> [<model2> ...] [MODE]

MODE (last arg, optional; default 'rename'):
  verbatim   - return a file unchanged        (MAX reuse; suffix best case)
  rename     - return the file with a rename   (high reuse, some divergence)
  generation - write novel code from scratch   (LOW reuse; suffix worst case)

Reports tok/s per model + the ratio vs the FIRST model (treated as the OFF
baseline). A big ratio on 'verbatim' with a ratio<=1 on 'generation' is the
signature of a decode where suffix helps reuse but the verify cost dominates on
novel text (the MoE concern; see draft_cooldown).
"""
import sys, time, json, urllib.request

BASE = "http://localhost:8000/v1/chat/completions"
_MODES = {"verbatim", "rename", "generation"}
MODE = sys.argv[-1] if sys.argv[-1] in _MODES else "rename"
MODELS = [a for a in sys.argv[1:] if a not in _MODES]

FILE = "".join(
    f"def op_{i}(x, y):\n    # combine two values for step {i}\n    z = x + y * {i}\n    return z\n\n"
    for i in range(40)
)
if MODE == "verbatim":
    PROMPT = "Return this file VERBATIM, unchanged. Output only the code.\n\n" + FILE
    MAXTOK = 1200
elif MODE == "generation":
    PROMPT = ("Write a Python module implementing an LRU cache class `LRUCache` with O(1) "
              "get/put using a dict + doubly-linked list, a `Trie` class with insert/search, "
              "and a `merge_intervals(intervals)` function. Include docstrings.")
    MAXTOK = 600
else:  # rename
    PROMPT = ("Return this file VERBATIM, but rename every function `op_<n>` to `apply_<n>` "
              "(keep everything else identical). Output only the code.\n\n" + FILE)
    MAXTOK = 1200

def run(model):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": MAXTOK, "temperature": 0.4, "top_p": 0.95, "top_k": 20,
        "min_p": 0.0, "thinking_budget": 1,
    }).encode()
    req = urllib.request.Request(BASE, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=1800) as r:
        d = json.load(r)
    dt = time.perf_counter() - t0
    ct = (d.get("usage") or {}).get("completion_tokens", 0)
    return dt, ct, (ct / dt if dt else 0.0)

print(f"=== MODE={MODE} ===", flush=True)
base_tps = None
for i, m in enumerate(MODELS):
    dt, ct, tps = run(m)
    if i == 0:
        base_tps = tps
    ratio = f"  ratio-vs-first {tps / base_tps:.2f}x" if base_tps else ""
    print(f"{m}: {ct} tok in {dt:.1f}s = {tps:.1f} tok/s{ratio}", flush=True)

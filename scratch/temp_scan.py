"""Token-capped temperature scan on HumanEval/146 for Qwen3.8-27B-mlx-uniform-4bit.

Purpose: HumanEval/146 ran away (>3600s, no self-termination) at temp 1.0 AND 0.7. This probe
walks temp down in 0.1 steps under a HARD max_tokens=8192 cap, so each non-converging draw costs
~7 min at the observed ~20 tok/s instead of an hour. Verdict per the silent-clamp rule:
converged iff finish_reason=="stop" AND completion_tokens < resolved_budget, where
resolved_budget = int(0.8 * min(max_tokens, cap - prompt_tokens)) — finish=="stop" alone is a
FALSE PASS (ThinkingBudgetCriteria force-injects </think> at the resolved budget).

One draw per temp: request seeds are inert on this serving path (O28), so k>1 = byte copies.
This is a PROBE informing which official ladder rung to run — its rows are not scored results.

Run (after the t0.7 rung finishes; one resident model, no concurrent requests):
    PYTHONPATH=$STACK_REPO/benchmark $STACK_REPO/.venv-bench/bin/python temp_scan_he146.py
"""
import json
import sys
import time

from bench import benchmarks, client, model_params

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--model", required=True)
_ap.add_argument("--item", required=True)
_ap.add_argument("--temps", required=True, help="comma list, e.g. 0.5,0.4,0.3,0.2")
_ap.add_argument("--out", required=True)
_args, _ = _ap.parse_known_args()
MODEL = _args.model
ITEM_ID = _args.item
MAX_TOKENS = 8192
TEMPS = [float(t) for t in _args.temps.split(",")]
CLAMP_RATIO = 0.8   # mirror of THINKING_BUDGET_CLAMP_RATIO (mlx-vlm generation.py:535)

def main():
    items = {i["id"]: i for i in benchmarks.load("humanevalplus", None, 0)}
    it = items[ITEM_ID]
    messages = benchmarks.build_messages("humanevalplus", it)
    out_path = _args.out
    results = []
    client.preload(MODEL)
    for t in TEMPS:
        params = model_params.params_for(MODEL, profile="deployed")
        params["temperature"] = t
        params["max_tokens"] = MAX_TOKENS
        params["thinking_budget"] = MAX_TOKENS  # server clamps to 0.8*effective anyway
        t0 = time.time()
        try:
            p = client.probe(MODEL, messages, params, timeout=900)
        except Exception as e:  # timeout/HTTP error = non-converged at this temp, keep scanning
            row = {"temp": t, "error": str(e)[:200], "wall_s": round(time.time() - t0, 1),
                   "converged": False}
            results.append(row)
            print(json.dumps(row), flush=True)
            continue
        ct = p.get("completion_tokens")
        pt = p.get("prompt_tokens") or 0
        resolved = int(CLAMP_RATIO * min(MAX_TOKENS, 262144 - pt))
        conv = (p.get("finish_reason") == "stop") and ct is not None and ct < resolved
        row = {"temp": t, "completion_tokens": ct, "prompt_tokens": pt,
               "finish_reason": p.get("finish_reason"), "resolved_budget": resolved,
               "converged": conv, "wall_s": round(time.time() - t0, 1),
               "decode_tps": p.get("decode_tps"),
               "tail": ((p.get("reasoning") or "") + (p.get("content") or ""))[-200:]}
        results.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "tail"}), flush=True)
    with open(out_path, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    conv_temps = [r["temp"] for r in results if r.get("converged")]
    print(f"\nconverged at temps: {conv_temps or 'NONE'}", flush=True)

if __name__ == "__main__":
    main()

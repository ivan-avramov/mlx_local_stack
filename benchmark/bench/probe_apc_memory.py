"""Measure APC's memory HIGH-WATER MARK, to decide whether it can cost a candidate its gate.

THE QUESTION (operator, 2026-08-13): APC is acceptable if it buys TTFT for free, but NOT if it eats
memory that pushes a model out of consideration against the <=46GB @256K gate.

TWO CODE FACTS THAT REFRAME IT (both read from the fork, not assumed):
  1. THE POOL IS LAZY. `APCManager.__init__` builds `[APCBlock(block_id=i) for i in
     range(num_blocks)]`, and `APCBlock` is a dataclass whose `components` dict starts EMPTY
     (apc.py:531-544) -- no KV tensors at construction. So APC's cost is a HIGH-WATER MARK that
     grows as real prefixes get cached, bounded above by num_blocks x per-block KV bytes. It is
     NOT a reservation, which is how "APC_NUM_BLOCKS=16384 costs ~33GB" should be read: that was
     a ceiling being approached, not claimed at startup.
  2. THE CEILING HAS A UNITS-FREE READING. blocks x block_size tokens = the cache capacity in
     TOKENS (block_size 16, apc.py:65). At the shipped 2048 blocks that is 32,768 tokens, so
     "APC costs at most the KV of 32K extra context FOR THIS MODEL" -- which makes the cost
     kv_bits-dependent, and therefore ~4x smaller on the 4-bit-KV distill than on fp16-KV Ornith.

WHY MEASURING ORNITH SETTLES THE BINDING CASE. The distill has the tight headroom (43.3GB @256K vs
the 46GB gate = 2.7GB) but the SMALLER pool (4-bit KV). Ornith has the larger pool (fp16 KV) but
13.4GB of headroom. So if fp16-KV Ornith's high-water mark fits inside 2.7GB, the distill's -- being
roughly a quarter of it -- certainly does, and neither candidate is at risk. That is a conservative
one-model argument, not an extrapolation from the easy case.

METHOD. Send N requests whose prefixes are LONG and mutually UNIQUE, so nothing is reused and the
pool is forced to fill rather than hit. Total prefix tokens are chosen to exceed the pool capacity,
so the measured mark is the CEILING, not whatever a light session happened to touch. The caller runs
this once with APC absent from the router env and once with APC_ENABLED=1, and diffs.

`max_tokens` is capped here and that is deliberate and legitimate: this probe measures PREFILL and
KV residency, so decode length is irrelevant to the endpoint. Thinking stays ENABLED (AGENTS.md
forbids switching it off to make a run work), it is simply cut short by the cap.

Reports `mx.get_peak_memory` (the campaign's gate metric, via the server's peak_mem_gb) as the
headline, and prompt tokens actually prefilled so the pool-fill claim is auditable.

  cd benchmark && PYTHONPATH=. ../.venv/bin/python -m bench.probe_apc_memory \
      --model Ornith-1.0-35B-mlx-uniform-4bit --label apc_off
"""
import argparse
import json
import os
import time

from .driver import MlxServeDriver

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

# ~4.6 chars/token on these tokenizers (measured cpt=4.61), so this line is ~16 tokens.
_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "

# Memory only -- decode length is not the endpoint. Thinking stays on.
PARAMS = {
    "temperature": 0.4,
    "top_p": 0.95,
    "top_k": 20,
    "min_p": 0.0,
    "presence_penalty": 0.0,
    "max_tokens": 8,
    "thinking_budget": 81920,
    "enable_thinking": True,
}

POOL_TOKENS_AT_2048_BLOCKS = 2048 * 16       # apc.py DEFAULT_NUM_BLOCKS x DEFAULT_BLOCK_SIZE


def unique_prefix(idx: int, approx_tokens: int, cpt: float = 4.61) -> str:
    """A long prefix that CANNOT prefix-match any other request.

    The unique marker goes FIRST: APC matches on prefixes, so a shared head with a unique tail
    would still hit, and the pool would fill with far less than intended.
    """
    head = f"Document {idx} of an unrelated corpus, id {idx * 7919}. "
    n = max(1, int(approx_tokens * cpt / len(_FILLER)))
    return head + (_FILLER * n)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="APC memory high-water-mark probe.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True, help="apc_off | apc_on (the router env state; "
                                                   "recorded verbatim, NOT verified here)")
    ap.add_argument("--requests", type=int, default=5)
    ap.add_argument("--tokens-per-request", type=int, default=9000)
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    driver = MlxServeDriver()
    t = driver.preload(args.model)
    print(f"[apc] preloaded {args.model} in {t}s (label={args.label})", flush=True)

    total_target = args.requests * args.tokens_per_request
    print(f"[apc] driving {args.requests} UNIQUE prefixes x ~{args.tokens_per_request} tok "
          f"= ~{total_target} tok vs pool capacity {POOL_TOKENS_AT_2048_BLOCKS} tok "
          f"({'EXCEEDS -> measures the CEILING' if total_target > POOL_TOKENS_AT_2048_BLOCKS else 'BELOW -> under-fills, invalid'})",
          flush=True)

    draws = []
    for i in range(args.requests):
        msg = unique_prefix(i, args.tokens_per_request)
        r = driver.complete(args.model, [{"role": "user", "content": msg + "\n\nReply: OK"}],
                            dict(PARAMS), timeout=args.timeout)
        d = {"req": i, "prompt_tokens": r.get("prompt_tokens"),
             "completion_tokens": r.get("completion_tokens"),
             "peak_mem_gb": r.get("peak_mem_gb"), "prefill_s": r.get("prefill_s"),
             "prefill_tps": r.get("prefill_tps"), "wall_s": r.get("wall_s")}
        draws.append(d)
        print(f"[apc] req{i} prompt={d['prompt_tokens']} peak_mem_gb={d['peak_mem_gb']} "
              f"prefill={d['prefill_s']}s ({d['prefill_tps']} tok/s) wall={d['wall_s']}s",
              flush=True)

    peaks = [d["peak_mem_gb"] for d in draws if d["peak_mem_gb"] is not None]
    prefilled = sum(d["prompt_tokens"] or 0 for d in draws)
    result = {
        "model": args.model, "axis": "apc_memory", "apc_label": args.label,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "params": PARAMS, "requests": args.requests,
        "tokens_per_request": args.tokens_per_request,
        "pool_capacity_tokens_at_2048_blocks": POOL_TOKENS_AT_2048_BLOCKS,
        "total_prompt_tokens_prefilled": prefilled,
        "pool_capacity_exceeded": prefilled > POOL_TOKENS_AT_2048_BLOCKS,
        "max_peak_mem_gb": max(peaks) if peaks else None,
        "draws": draws,
    }
    out = args.out or os.path.join(RESULTS, args.model, f"apc_memory_{args.label}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[apc] RESULT label={args.label} max_peak_mem_gb={result['max_peak_mem_gb']} "
          f"prefilled={prefilled} pool_capacity_exceeded={result['pool_capacity_exceeded']}",
          flush=True)
    print(f"[apc] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

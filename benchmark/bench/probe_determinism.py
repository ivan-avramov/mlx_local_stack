"""Determinism isolation probe — is unseeded output reproducible, and does that depend
on suffix decoding or on tail TRUNCATION?

WHY THIS EXISTS. AGENTS.md records that an unseeded request returns BYTE-IDENTICAL text
(the server keys its sampler deterministically per request, DEFAULT_SEED=0). The Tier-0
grid (2026-08-12) contradicted that: two cells with BYTE-IDENTICAL params — `t0.4_mp0.0`
and `collapse_minp_only`, verified identical field-by-field — produced 2,941 vs 2,841
completion tokens on `run_convergence`'s HARDCODED coding prompt (a constant string, so
neither `cpt` nor a task seed can explain it). Meanwhile three OTHER cells that differed
only in inert knobs (`t0.4_mp0.02` / `t0.4_mp0.05` / `collapse_3knob`) were exactly equal
at 3,136 tokens. So determinism held in some cells and failed in others.

The cells that REPRODUCED all had at least one tail-truncation knob active; the pair that
DIVERGED had all three off (top_p 1.0, top_k 0, min_p 0.0), i.e. the sampler ranged over
the full vocabulary. That suggests the divergence is numeric noise in the low-probability
TAIL flipping a sampled token — noise that any active truncation clips away before it can
matter. Suffix (n-gram draft) decoding is one candidate source of that noise, which is why
AGENTS.md calls it "inherently non-lossless — kernel numerics flip greedy argmaxes".

So the naive test ("run one config twice with suffix ON, twice with OFF") is CONFOUNDED: at
the deployed config truncation is active, so it would reproduce under BOTH suffix states and
falsely exonerate suffix. Truncation has to be a FACTOR, not a constant:

    2x2:  suffix {ON, OFF}  x  truncation {ON (deployed 0.95/20), OFF (1.0/0/0.0)}

Reading the result:
  - diverges only when truncation OFF, in BOTH suffix states -> suffix EXONERATED; the noise
    is elsewhere (Metal reduction order, MoE routing, batching) and truncation masks it.
  - diverges when truncation OFF under suffix ON but NOT under suffix OFF -> suffix IS the
    source, and the deployed config only hides it.
  - reproduces everywhere -> the Tier-0 divergence was not a sampling-path property; look at
    what else differed between those two runs.

Byte-identity is the actual claim, so this hashes the returned TEXT. `run_convergence`
persists only token counts, which is a proxy, not the claim.

Suffix decoding is a REGISTRY setting (`draft_kind: suffix`), so this probe does NOT toggle
it — the caller flips the registry and restarts the router between invocations, passing
--label to say which state is live. The probe records the label verbatim; it cannot verify it.

  cd benchmark && PYTHONPATH=. ../.venv/bin/python -m bench.probe_determinism \
      --model Ornith-1.0-35B-mlx-uniform-4bit --label suffix_on --reps 3
"""
import argparse
import hashlib
import json
import os
import time

from .driver import MlxServeDriver
from .run_convergence import CODING_PROMPT

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

# The two truncation states. Everything else is held at the deployed values, and NO seed is
# sent — an explicit seed would make the whole question moot, since the unseeded path is
# exactly what every benchmark row and every client request actually uses.
BASE = {
    "temperature": 0.4,
    "presence_penalty": 0.0,   # nonzero would DISABLE suffix decoding = different path
    "max_tokens": 102400,
    "thinking_budget": 81920,
    "enable_thinking": True,
}
TRUNCATION = {
    # deployed: top_p/top_k clip the tail
    "on": {"top_p": 0.95, "top_k": 20, "min_p": 0.0},
    # the anomalous Tier-0 config: nothing clips the tail
    "off": {"top_p": 1.0, "top_k": 0, "min_p": 0.0},
}


def _sha(s: str) -> str:
    return hashlib.sha256((s or "").encode()).hexdigest()[:16]


def run_cell(driver, model, trunc_state: str, reps: int, timeout: float) -> dict:
    params = dict(BASE, **TRUNCATION[trunc_state])
    draws = []
    for i in range(reps):
        r = driver.complete(model, [{"role": "user", "content": CODING_PROMPT}],
                            dict(params), timeout=timeout)
        d = {
            "rep": i,
            "content_sha": _sha(r.get("content")),
            "reasoning_sha": _sha(r.get("reasoning")),
            "completion_tokens": r.get("completion_tokens"),
            "content_chars": len(r.get("content") or ""),
            "reasoning_chars": len(r.get("reasoning") or ""),
            "finish_reason": r.get("finish_reason"),
            "wall_s": r.get("wall_s"),
            "decode_tps": r.get("decode_tps"),
        }
        draws.append(d)
        print(f"[det] trunc={trunc_state} rep={i} ct={d['completion_tokens']} "
              f"csha={d['content_sha']} rsha={d['reasoning_sha']} "
              f"wall={d['wall_s']}s", flush=True)
    # byte-identity over the FULL returned text (reasoning + content), which is the claim
    sigs = {(d["content_sha"], d["reasoning_sha"]) for d in draws}
    tok = {d["completion_tokens"] for d in draws}
    return {
        "truncation": trunc_state,
        "params": params,
        "draws": draws,
        "distinct_text_signatures": len(sigs),
        "distinct_token_counts": len(tok),
        "byte_identical": len(sigs) == 1,
        # a token-count tie with differing text would mean the count proxy Tier-0 relied on
        # is WEAKER than it looks; worth knowing explicitly
        "token_count_agrees_with_text": (len(tok) == 1) == (len(sigs) == 1),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Determinism isolation probe (2x2 with suffix).")
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", required=True,
                    help="suffix state that the CALLER has made live in the registry, e.g. "
                         "suffix_on / suffix_off. Recorded verbatim; NOT verified here.")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--truncation", choices=["on", "off", "both"], default="both")
    ap.add_argument("--no-preload", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    driver = MlxServeDriver()
    if not args.no_preload:
        t = driver.preload(args.model)
        print(f"[det] preloaded {args.model} in {t}s (label={args.label})", flush=True)

    states = ["on", "off"] if args.truncation == "both" else [args.truncation]
    cells = [run_cell(driver, args.model, s, args.reps, args.timeout) for s in states]

    result = {
        "model": args.model,
        "axis": "determinism_isolation",
        "suffix_label": args.label,
        "reps": args.reps,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "cells": cells,
    }
    out = args.out or os.path.join(RESULTS, args.model, f"determinism_{args.label}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    for c in cells:
        print(f"[det] VERDICT label={args.label} truncation={c['truncation']} "
              f"byte_identical={c['byte_identical']} "
              f"distinct_text_sigs={c['distinct_text_signatures']}/{args.reps}", flush=True)
    print(f"[det] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

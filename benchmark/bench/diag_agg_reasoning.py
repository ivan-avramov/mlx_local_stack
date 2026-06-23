"""Capture the FULL reasoning text from ONE CWE aggregation sample, to see exactly WHAT the
model does in <think> when it rambles to the thinking budget. Hypothesis: the CWE task
(find the 5 most-frequent words among ~2000 distinct pseudo-words appearing ~6000 times)
forces the model to TALLY thousands of nonsense words, which legitimately needs >16K tokens.

Same seed as run_convergence trial 0 (agg_ctx*1000) so the scenario matches the ladder runs.

  PYTHONPATH=. <py> -m bench.diag_agg_reasoning --model X [--temperature T] [--budget B] [--ctx N]
"""
import argparse
import os

from .driver import MlxServeDriver
from .model_params import params_for
from .aggregation import build_cwe, score_cwe

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--budget", type=int, default=16384)
    ap.add_argument("--ctx", type=int, default=8000)
    ap.add_argument("--seed", type=int, default=None, help="default = ctx*1000 (conv trial 0)")
    a = ap.parse_args(argv)

    d = MlxServeDriver()
    print(f"[cap] preloaded in {d.preload(a.model)}s", flush=True)
    p = params_for(a.model)
    p["thinking_budget"] = a.budget
    if a.temperature is not None:
        p["temperature"] = a.temperature
    seed = a.seed if a.seed is not None else a.ctx * 1000
    ctx, targets, q = build_cwe(a.ctx, 4.6, k=5, seed=seed)
    words = ctx.split()
    print(f"[cap] ctx_words={len(words)} distinct_words={len(set(words))} "
          f"targets(30x each)={targets} temp={p['temperature']} budget={a.budget}", flush=True)

    r = d.complete(a.model, [{"role": "user", "content": ctx + "\n\n" + q}], p)
    reasoning = r.get("reasoning") or ""
    content = r.get("content") or ""
    print(f"[cap] finish={r.get('finish_reason')} comp_tok={r.get('completion_tokens')} "
          f"reasoning_chars={len(reasoning)} content={content!r} "
          f"acc={score_cwe(content, targets)} tps={r.get('decode_tps')}", flush=True)

    os.makedirs(RESULTS, exist_ok=True)
    safe = a.model.replace("/", "_")
    out = os.path.join(RESULTS, f"_capture_{safe}_t{p['temperature']}_b{a.budget}.txt")
    with open(out, "w") as f:
        f.write(f"MODEL: {a.model}\nTARGETS (30x each): {targets}\nQUESTION: {q}\n"
                f"distinct_words={len(set(words))} total_words={len(words)}\n"
                f"finish={r.get('finish_reason')} comp_tok={r.get('completion_tokens')} "
                f"reasoning_chars={len(reasoning)} acc={score_cwe(content, targets)}\n\n"
                f"=== CONTENT (answer) ===\n{content}\n\n"
                f"=== REASONING ({len(reasoning)} chars) ===\n{reasoning}\n")
    print(f"[cap] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

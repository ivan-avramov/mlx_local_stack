#!/usr/bin/env python3
"""mlx_local_stack reasoning+coding benchmark harness.

Drives the mlx-serve router (:8000) over HTTP. Two phases:
  generate  — slow, chunked, resumable; produces per-item completions on disk.
  grade     — fast, mechanical; scores the saved completions (no model calls).

Escalation workflow: run --tier light across all models, grade, see where you are, then
--tier mid (regenerates only the new items, reusing light), then --tier heavy.

Examples:
  uv run python benchmark/run.py list
  uv run python benchmark/run.py generate --tier light --chunks all     # first pass, all models
  uv run python benchmark/run.py grade    --tier light
  uv run python benchmark/run.py generate --tier mid   --chunks all     # adds only new items
  uv run python benchmark/run.py status   --tier mid
  uv run python benchmark/run.py generate --models gemma-4-26B-A4B-it-QAT-MLX-4bit --benches aime --limit aime=5
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import benchmarks, client, generate, grade, model_params  # noqa: E402

# Escalating tiers, NESTED: light's items are a prefix of mid's are a prefix of heavy's
# (same seed), and light benches ⊆ mid ⊆ heavy. So run light across all models, grade, then
# `--tier mid` only generates the *additional* items (resume reuses light), then heavy.
# Cost note (real params): reasoning items ~5h/item across all 7; coding cheaper. light is
# coding-led for a fast first read + calibrates real coding cost; mid adds math reasoning;
# heavy = full sets + GPQA. All tunable via --limit / --models.
TIERS = {
    "light": (["humanevalplus", "mbppplus", "aime"],
              {"humanevalplus": 15, "mbppplus": 15, "aime": 5}),
    "mid":   (["humanevalplus", "mbppplus", "livecodebench", "ifeval", "aime", "math500"],
              {"humanevalplus": 40, "mbppplus": 40, "livecodebench": 15, "ifeval": 30, "aime": 30, "math500": 30}),
    "heavy": (["humanevalplus", "mbppplus", "livecodebench", "ifeval", "aime", "math500", "gpqa"],
              {"humanevalplus": 164, "mbppplus": 378, "livecodebench": 100, "ifeval": 541, "aime": 60, "math500": 200, "gpqa": 198}),
}


def _parse_kv(s):
    out = {}
    for part in (s or "").split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = int(v)
    return out


def _resolve(args):
    if getattr(args, "tier", None):
        benches, limits = TIERS[args.tier]
        benches = list(benches)
        limits = dict(limits)
    else:
        benches = [b.strip() for b in args.benches.split(",")] if args.benches else list(benchmarks.SPECS)
        limits = {}
    limits.update(_parse_kv(getattr(args, "limit", "")))
    models = [m.strip() for m in args.models.split(",")] if args.models else client.roster()
    return models, benches, limits


def cmd_list(args):
    print("Benchmarks:")
    for name, spec in benchmarks.SPECS.items():
        avail = "?"
        try:
            n = len(benchmarks.load(name, limit=1, seed=0))
            avail = f"ok (sample loads, {n} item)"
        except Exception as e:  # noqa: BLE001
            avail = f"UNAVAILABLE: {type(e).__name__}: {str(e)[:70]}"
        gate = " [gated: needs HF_TOKEN]" if spec["gated"] else ""
        print(f"  {name:<15} {spec['kind']:<9} ans={spec['answer_type']:<5}{gate}  -> {avail}")
    print("\nServed models (with production params):")
    for m in client.roster():
        p = model_params.params_for(m)
        print(f"  {m:<34} temp={p['temperature']} top_p={p['top_p']} "
              f"max_tok={p['max_tokens']} thinking_budget={p['thinking_budget']}")


def cmd_generate(args):
    models, benches, limits = _resolve(args)
    overrides = {}  # global params layered over each model's production config
    if args.thinking_budget is not None:
        overrides["thinking_budget"] = args.thinking_budget
    if args.temp is not None:
        overrides["temperature"] = args.temp
    if args.max_tokens is not None:
        overrides["max_tokens"] = args.max_tokens
    chunks = "all" if args.chunks in ("all", "-1") else args.chunks
    print(f"[params] using per-model production params (model_params.py); overrides={overrides or 'none'}")
    generate.run(models, benches, limits, seed=args.seed, chunk_minutes=args.chunk_minutes,
                 chunks=chunks, overrides=overrides, order=args.order)


def cmd_grade(args):
    models, benches, limits = _resolve(args)
    scores = grade.grade_all(models, benches)
    print(f"\n{'model':<34}{'benchmark':<15}{'n':>5}{'acc':>9}{'err':>5}{'conv%':>7}  valid")
    print("-" * 86)
    invalid = []
    for s in scores:
        acc = f"{s['acc']*100:.1f}%" if s.get("acc") is not None else (s.get("note", "—")[:30])
        cr = s.get("convergence_rate")
        conv = f"{cr*100:.0f}" if cr is not None else "—"
        ok = s.get("valid")
        flag = "OK" if ok else ("INVALID" if ok is False else "—")
        if ok is False:
            invalid.append(s)
        print(f"{s['model']:<34}{s['benchmark']:<15}{s.get('n', 0):>5}{acc:>9}{s.get('errors', 0):>5}{conv:>7}  {flag}")
        bd = s.get("by_difficulty")
        if bd:
            cells = "  ".join(f"{d}:{v['pass@1']*100:.0f}%(n={v['n']})"
                               for d, v in sorted(bd.items()))
            print(f"      by difficulty: {cells}")
    print("\nconv% = share of items that CONVERGED (finish=stop AND tokens < thinking_budget)")
    if invalid:
        print("\n⚠️  INVALID runs — looped/truncated items present (NOT a clean result; investigate "
              "stale router or quant loop, do NOT report acc):")
        for s in invalid:
            print(f"   {s['model']} / {s['benchmark']}: loops {s.get('loop_ids')}")
    print("Full scores -> benchmark/results/scores.json")


def cmd_status(args):
    models, benches, limits = _resolve(args)
    print(f"{'model':<34}{'benchmark':<15}{'done':>6}{'target':>8}")
    print("-" * 64)
    for model in models:
        for b in benches:
            target = len(benchmarks.load(b, limits.get(b), args.seed)) if _safe_load(b) else "?"
            done = len(generate.done_ids(model, b))
            print(f"{model:<34}{b:<15}{done:>6}{str(target):>8}")


def _safe_load(b):
    try:
        benchmarks.load(b, 1, 0)
        return True
    except Exception:
        return False


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--models", default=None, help="comma list; default = all served")
        sp.add_argument("--benches", default=None, help="comma list; e.g. aime,gpqa")
        sp.add_argument("--tier", choices=list(TIERS), default=None,
                        help="light|mid|heavy — nested escalating scope (run light first, then mid, then heavy)")
        sp.add_argument("--limit", default="", help="per-bench cap, e.g. aime=20,gpqa=15")
        sp.add_argument("--seed", type=int, default=0)

    sp = sub.add_parser("list"); sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("generate"); common(sp); sp.set_defaults(func=cmd_generate)
    sp.add_argument("--chunks", default="all", help="N chunks then stop (runway), or 'all'")
    sp.add_argument("--chunk-minutes", type=float, default=30.0)
    sp.add_argument("--order", choices=["roundrobin", "model"], default="roundrobin",
                    help="roundrobin: balanced prefix across all models (default); model: one model at a time")
    sp.add_argument("--max-tokens", dest="max_tokens", type=int, default=None,
                    help="override max_tokens for all models (default: each model's config value)")
    sp.add_argument("--temp", type=float, default=None, help="override temperature for all models")
    sp.add_argument("--thinking-budget", dest="thinking_budget", type=int, default=None,
                    help="override thinking_budget for all models (default: config value — "
                         "16384 Gemma / 49152 Qwen). Lower it to bound eval time.")

    sp = sub.add_parser("grade"); common(sp); sp.set_defaults(func=cmd_grade)
    sp = sub.add_parser("status"); common(sp); sp.set_defaults(func=cmd_status)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

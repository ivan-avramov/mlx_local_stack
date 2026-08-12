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
    restart_fn = None
    if args.auto_restart_on_loop:
        from bench import preflight
        restart_fn = preflight.restart_router
        print("[generate] auto-restart-on-loop ENABLED (looped item -> fresh router + 1 retry)")
    print(f"[generate] sampling profile = {args.sampling_profile}")
    print(f"[generate] per-probe HTTP timeout = {args.probe_timeout}s")
    if args.clean_stale:
        print("[generate] --clean-stale ENABLED (delete + regenerate any results whose config differs)")
    generate.run(models, benches, limits, seed=args.seed, chunk_minutes=args.chunk_minutes,
                 chunks=chunks, overrides=overrides, order=args.order, restart_fn=restart_fn,
                 sampling_profile=args.sampling_profile, probe_timeout=args.probe_timeout,
                 clean_stale=args.clean_stale, samples=args.samples, seed_base=args.seed_base)


def cmd_grade(args):
    models, benches, limits = _resolve(args)
    scores = grade.grade_all(models, benches)
    # 44, not 34: `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` is 35 chars and ran into the next column,
    # and these rows get pasted straight into campaign-results.md.
    hdr = (f"\n{'model':<44}{'benchmark':<14}{'n':>4}{'k':>3}{'acc':>8}{'95% CI':>16}"
           f"{'MDE':>7}{'conv%':>7}{'gate':>6}  harness")
    print(hdr)
    print("-" * len(hdr))
    broken, ungated = [], []
    for s in scores:
        acc = f"{s['acc']*100:.1f}%" if s.get("acc") is not None else (s.get("note", "—")[:30])
        ci = s.get("ci95")
        # A metric is NEVER printed without its interval and the axis resolution: an unadorned
        # 86.7% invites a ranking the sample size cannot support.
        k = s.get("samples") or 0
        ci_s = f"[{ci[0]*100:.0f},{ci[1]*100:.0f}]" if ci else ("—" if k > 1 else "n=1")
        mde_s = f"±{s['mde']*100:.0f}pp" if s.get("mde") is not None else "—"
        cr = s.get("conv_rate")
        conv = f"{cr*100:.0f}" if cr is not None else "—"
        gate = "PASS" if s.get("conv_gate_pass") else "FAIL"
        harness = "ok" if s.get("valid") else "BROKEN"
        if not s.get("valid"):
            broken.append(s)
        elif not s.get("conv_gate_pass"):
            ungated.append(s)
        print(f"{s['model']:<44}{s['benchmark']:<14}{s.get('n', 0):>4}{k:>3}{acc:>8}{ci_s:>16}"
              f"{mde_s:>7}{conv:>7}{gate:>6}  {harness}")
        extra = []
        if s.get("pass_at_1_converged") is not None:
            extra.append(f"pass@1|conv={s['pass_at_1_converged']*100:.1f}% "
                         f"(n={s.get('n_converged_items')})")
        if s.get("acc_strict") is not None:
            extra.append(f"strict@{s.get('acc_strict_budget')}={s['acc_strict']*100:.1f}%")
        if s.get("nonconv_kinds"):
            extra.append("nonconv=" + ",".join(f"{kk}:{vv}" for kk, vv in sorted(s["nonconv_kinds"].items())))
        if s.get("n_contaminated"):
            extra.append(f"contaminated={s['n_contaminated']} (excluded from acc)")
        rel = s.get("reliability")
        if rel:
            extra.append("reliability c_i=" + ",".join(f"{c}x{n}" for c, n in sorted(rel["histogram"].items(), reverse=True)))
        if extra:
            print("      " + " | ".join(extra))
        bd = s.get("by_difficulty")
        if bd:
            cells = "  ".join(f"{d}:{v['pass@1']*100:.0f}%(n={v['n']})"
                               for d, v in sorted(bd.items()))
            print(f"      by difficulty: {cells}")
    print("\nDECISION RULE (pre-registered): conv% >= 90 is a GATE; pass@1|conv RANKS within it.")
    print("acc = correctness over generated items (historical meaning). strict@<budget> counts a")
    print("truncated draw as failed — a DERIVED deployment number, never the ranking key (it rises")
    print("with thinking_budget). 'harness' is BROKEN only when the HARNESS failed, not the model.")
    if ungated:
        print("\n⚠️  below the convergence gate — these models did not self-terminate often enough;")
        print("    investigate the mechanism (nonconv kinds above), do NOT rank on pass@1 alone:")
        for s in ungated:
            print(f"   {s['model']} / {s['benchmark']}: conv {s['conv_rate']*100:.0f}% "
                  f"kinds={s.get('nonconv_kinds')}")
    if broken:
        print("\n⛔ HARNESS-BROKEN runs (errors, not model behaviour) — fix and re-run:")
        for s in broken:
            print(f"   {s['model']} / {s['benchmark']}: {s.get('note')}")
    print(f"Full scores -> {generate.results_root()}/scores.json")


def cmd_compare(args):
    """Paired head-to-head between two models on one bench, with a verdict that can be
    'inconclusive'. Refuses any comparison the data cannot support rather than printing a delta."""
    from bench import compare as CMP
    models, benches, _ = _resolve(args)
    if len(models) != 2:
        print("compare needs exactly two --models"); return
    for b in benches:
        r = CMP.compare(models[0], models[1], b, margin=args.margin)
        print(f"\n=== {b}: {models[0]}  vs  {models[1]}")
        if not r["comparable"]:
            print(f"  NOT COMPARABLE — {r['reason']}")
            continue
        d = r["delta"]
        print(f"  matched items: {r['n_items']}   samples: {r['samples']}   axis MDE: ±{r['mde']*100:.0f}pp")
        print(f"  {r['metric']}: {r['a']*100:.1f}% vs {r['b']*100:.1f}%")
        print(f"  delta {d['delta']*100:+.1f}pp   95% CI [{d['lo']*100:+.1f}, {d['hi']*100:+.1f}]pp")
        print(f"  VERDICT: {d['verdict'].upper()}")
        if d["verdict"] == "inconclusive":
            print(f"  (the interval spans 0 and is wider than the ±{args.margin*100:.0f}pp "
                  f"equivalence margin — this is NOT evidence of a tie; it is too little data. "
                  f"{r['n_for_margin']} matched items would be needed.)")
        for w in r.get("warnings", []):
            print(f"  ⚠️  {w}")


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
    sp.add_argument("--auto-restart-on-loop", dest="auto_restart_on_loop", action="store_true",
                    help="on a looped/truncated item, restart the router + re-probe once; "
                         "classify recovered (stale router) vs loop_persisted (genuine quant loop)")
    sp.add_argument("--sampling-profile", dest="sampling_profile",
                    choices=model_params.profile_names(), default="production",
                    help="production = daily-driver opencode.json config (default); "
                         "official = each family's published recommended sampling (quality eval); "
                         "coding = converging sampling + a thinking_budget large enough to not "
                         "truncate hard-problem reasoning")
    sp.add_argument("--probe-timeout", dest="probe_timeout", type=int, default=3600,
                    help="per-item HTTP timeout (s). Raise for slow dense models whose thinking "
                         "budget implies >60min generation (e.g. Qwen3.6-27B @ ~13.5 tok/s, 80K "
                         "budget ~100min → use ~9000). Default 3600.")
    sp.add_argument("--samples", type=int, default=1,
                    help="draws per item (k). Each draw gets its own seed — WITHOUT that the "
                         "server returns byte-identical text and reliability reads as perfect. "
                         "k buys RELIABILITY, not power: at N=15, k=1->5 shrinks the SD only "
                         "12.7->10.8pp, while 5x the items gives -55%. Use k=2-3 and spend the "
                         "rest on items.")
    sp.add_argument("--seed-base", dest="seed_base", type=int, default=0,
                    help="shift every draw's seed (for an independent replication of a run that "
                         "already exists on disk)")
    sp.add_argument("--clean-stale", dest="clean_stale", action="store_true",
                    help="delete + regenerate any existing results whose recorded config "
                         "(sampling/profile/KV) differs from this run, instead of resuming on "
                         "top of them (which would mix provenance). Default: warn + keep.")

    sp = sub.add_parser("grade"); common(sp); sp.set_defaults(func=cmd_grade)
    sp = sub.add_parser("status"); common(sp); sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("compare"); common(sp); sp.set_defaults(func=cmd_compare)
    sp.add_argument("--margin", type=float, default=0.05,
                    help="equivalence margin for the TOST verdict (default 5pp)")

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""mlx_local_stack reasoning+coding benchmark harness.

Drives the mlx-serve router (:8000) over HTTP. Two phases:
  generate  — slow, chunked, resumable; produces per-item completions on disk.
  grade     — fast, mechanical; scores the saved completions (no model calls).

Escalation workflow: run --tier light across all models, grade, see where you are, then
--tier mid (regenerates only the new items, reusing light), then --tier heavy.

Examples:
  uv run python benchmark/run.py list
  uv run python benchmark/run.py generate --sampling-profile deployed --tier light --chunks all
  uv run python benchmark/run.py grade    --tier light
  uv run python benchmark/run.py generate --sampling-profile deployed --tier mid --chunks all
  uv run python benchmark/run.py status   --tier mid
  uv run python benchmark/run.py generate --sampling-profile deployed --models gemma-4-26B-A4B-it-QAT-MLX-4bit --benches aime --limit aime=5
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


def _parse_kv(s, benches=()):
    # C32: a part without "=" used to be SILENTLY DROPPED, so `--limit 5` meant
    # NO CAP and launched the full corpus. Now a bare integer broadcasts to every
    # requested bench (later `bench=N` parts override it), and anything else
    # REFUSES with a nonzero exit — never a silent no-cap.
    out = {}
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = int(v)
        elif part.isdigit() and benches:
            for b in benches:
                out.setdefault(b, int(part))
        else:
            raise SystemExit(
                f"[run] REFUSED: --limit part {part!r} is neither `bench=N` nor a "
                "bare integer with a bench list to apply it to. A silently ignored "
                "cap runs the FULL corpus (C32)."
            )
    return out


def _parse_ids(s):
    """`--ids ifeval=2849:279,humanevalplus=HumanEval/94` -> {bench: [id, ...]}.

    Colon separates ids because `--limit` already owns comma as its pair separator and ids can
    themselves contain commas. Returns None when empty, so the default path is untouched.
    """
    if not s or not s.strip():
        return None
    out = {}
    for part in s.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        bench, raw = part.split("=", 1)
        vals = [v.strip() for v in raw.split(":") if v.strip()]
        if vals:
            out.setdefault(bench.strip(), []).extend(vals)
    return out or None


def _resolve(args):
    if getattr(args, "tier", None):
        benches, limits = TIERS[args.tier]
        benches = list(benches)
        limits = dict(limits)
    else:
        benches = [b.strip() for b in args.benches.split(",")] if args.benches else list(benchmarks.SPECS)
        limits = {}
    limits.update(_parse_kv(getattr(args, "limit", ""), benches=benches))
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
    # O30 guard LIFTED 2026-09-02: per-request seeds reach the sampler on the deployed fork
    # (ab5273f + C26 ab5708a5 are ancestors of 57177a21) and the ruling's 2-seed byte-difference
    # probe passed on the live router (seeds 11 vs 22 differ; seed 11 reproduces). k>1 draws are
    # now genuine draws; seeds derive from (item, sample) so they stay paired across models.
    models, benches, limits = _resolve(args)
    overrides = {}  # global params layered over each model's production config
    if args.thinking_budget is not None:
        overrides["thinking_budget"] = args.thinking_budget
    if args.temp is not None:
        overrides["temperature"] = args.temp
    # The PENALTIES are provenance-tracked overrides like --temp, and they must be, for two reasons.
    # (1) Without a flag the only way to vary one is the registry `generation_defaults`, which marks
    # every existing row STALE and needs a router restart — unusable for an OFAT that varies ONE knob on
    # a FIXED item set. (2) A nonzero penalty also turns SUFFIX DECODING OFF (mlx-vlm
    # `generate/ar.py:163` — the block verify can apply no logits processor), so it changes the serving
    # path as well as the distribution. `compare` refuses across it and it is in the fingerprint's
    # sampling slice, so the override MUST reach the manifest, which it does via `overrides`.
    if args.presence_penalty is not None:
        overrides["presence_penalty"] = args.presence_penalty
    if args.repetition_penalty is not None:
        overrides["repetition_penalty"] = args.repetition_penalty
    if args.max_tokens is not None:
        overrides["max_tokens"] = args.max_tokens
    # depth_tokens (D9, coding-at-depth): prompt-side override, provenance-tracked via
    # `overrides` like the rest. A depth run must carry a tune label so its rows never share
    # a file with the shallow corpus (the fingerprint would catch the mix, but a separate
    # file is the difference between a refused resume and a poisoned one).
    if args.depth_tokens is not None:
        if not args.tune:
            print("[generate] REFUSED: --depth-tokens requires --tune (e.g. --tune d100k) so "
                  "depth rows get their own files and never collide with the shallow corpus.")
            raise SystemExit(2)
        overrides["depth_tokens"] = args.depth_tokens
    # reasoning_effort (M24): TEMPLATE-side knob — the Qwen3.8-27B family's chat template <!-- allow-shorthand -->
    # injects an effort instruction (default xhigh; Qwen3.6-family templates lack the knob). <!-- allow-shorthand -->
    # The server forwards it (mlx-vlm server/schemas.py), so it rides `overrides` into both
    # the request and the fingerprint's sampling slice. Requires --tune so effort rows get
    # their own files, never pooled with the template-default (xhigh) corpus.
    if args.reasoning_effort is not None:
        if not args.tune:
            print("[generate] REFUSED: --reasoning-effort requires --tune (e.g. --tune "
                  "t0.6-effmed) so effort rows get their own files and never collide with "
                  "the template-default corpus.")
            raise SystemExit(2)
        overrides["reasoning_effort"] = args.reasoning_effort
    chunks = "all" if args.chunks in ("all", "-1") else args.chunks
    tune = args.tune  # already grammar-validated by argparse's type=generate.validate_tune
    # Name the ACTUAL profile. This used to hardcode "production" and print immediately before
    # "[generate] sampling profile = deployed", i.e. it contradicted the next line. The manifest was
    # always right, but production-vs-deployed is exactly the distinction that decides whether a run
    # measured what we ship (`production` has DRIFTED: temp 0.7 / min_p 0.03 / presence_penalty 0.3,
    # and a nonzero presence_penalty also disables suffix decoding), so mislabelling it is dangerous.
    print(f"[params] sampling profile = {args.sampling_profile!r} (model_params.py); "
          f"overrides={overrides or 'none'}")
    restart_fn = None
    if args.auto_restart_on_loop:
        from bench import preflight
        restart_fn = preflight.restart_router
        print("[generate] auto-restart-on-loop ENABLED (looped item -> fresh router + 1 retry)")
    print(f"[generate] sampling profile = {args.sampling_profile}")
    probe_timeout = _resolve_probe_timeout(args, models, benches, tune)
    if args.clean_stale:
        print("[generate] --clean-stale ENABLED (delete + regenerate any results whose config differs)")
    generate.run(models, benches, limits, seed=args.seed, chunk_minutes=args.chunk_minutes,
                 chunks=chunks, overrides=overrides, order=args.order, restart_fn=restart_fn,
                 sampling_profile=args.sampling_profile, probe_timeout=probe_timeout,
                 clean_stale=args.clean_stale, samples=args.samples, seed_base=args.seed_base,
                 ids=_parse_ids(getattr(args, "ids", None)), tune=tune)


def _resolve_probe_timeout(args, models, benches, tune):
    """The client's patience, DERIVED (C28) unless the caller named it explicitly.

    A hardcoded bound below full-budget generation time is not a conservative choice — it is an
    active defect. The client gives up, the worker does NOT cancel, and the orphan starves the next
    item into a false DNF, which adds another orphan: M23's mbppplus leg collapsed into six
    consecutive false timeouts that way. A bound ABOVE the budget time means nothing is abandoned
    in normal operation, so no orphan is ever created, and a runaway terminates at max_tokens with
    a real token count instead of a contentless error row.

    The rate is MEASURED from the model's own rows (slow-tail percentile) and the run takes the
    most conservative bound across its models, since one bound covers the whole queue.
    """
    from bench import budget_timeout as BT, generate as G
    if getattr(args, "probe_timeout", None):
        print(f"[generate] per-probe HTTP timeout = {args.probe_timeout}s (EXPLICIT --probe-timeout)")
        return args.probe_timeout
    best, why = None, "no prior rows for these models"
    for m in models:
        rows = []
        for b in benches:
            try:
                rows += G.rows_for_rate(m, b)
            except Exception:  # noqa: BLE001 — a missing/unreadable bench must not block the run
                continue
        tps = BT.floor_decode_tps(rows)
        d = BT.derive_timeout(_thinking_budget_for(args, m), tps)
        if best is None or d["timeout_s"] > best:
            best, why = d["timeout_s"], f"{m}: {d['reason']}"
    print(f"[generate] per-probe HTTP timeout = {best:.0f}s (DERIVED, C28) — {why}")
    return int(best)


def _thinking_budget_for(args, model):
    """Resolved thinking budget for the model, so the bound is derived against the budget that will
    actually be served rather than a constant."""
    try:
        from bench import model_params
        return (model_params.params_for(model, profile=args.sampling_profile) or {}).get(
            "thinking_budget")
    except Exception:  # noqa: BLE001 — fall through to the ceiling rather than guess a budget
        return None


def cmd_grade(args):
    models, benches, limits = _resolve(args)
    scores = grade.grade_all(models, benches, tune=args.tune)
    # 44, not 34: `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` is 35 chars and ran into the next column,
    # and these rows get pasted straight into campaign-results.md.
    hdr = (f"\n{'model':<44}{'benchmark':<14}{'n':>4}{'k':>3}{'acc':>8}{'95% CI':>16}"
           f"{'MDE':>7}{'strict':>8}{'conv%':>7}{'degen':>7}  harness")
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
        # NOT a gate verdict: `conv_gate_pass` derives from the WITHDRAWN conv%>=90 threshold, so
        # printing PASS/FAIL here contradicted the footer. Show the degeneracy diagnostic instead —
        # a count of self-terminating repetition loops, which is real information and not a verdict.
        nd = s.get("n_degenerate_eosed")
        degen = "-" if not nd else str(nd)
        # acc_strict IS the ranking key at a matched budget (operator ruling 2026-08-13): a DNF is a
        # FAILURE in the denominator, so a model that DNFs 99 of 100 tasks scores 1%, not 100%. It was
        # previously buried in the detail line; a ranking key has to be in the table.
        st = s.get("acc_strict")
        strict_s = "—" if st is None else f"{st * 100:.1f}%"
        harness = "ok" if s.get("valid") else "BROKEN"
        if not s.get("valid"):
            broken.append(s)
        elif not s.get("conv_gate_pass"):
            ungated.append(s)
        print(f"{s['model']:<44}{s['benchmark']:<14}{s.get('n', 0):>4}{k:>3}{acc:>8}{ci_s:>16}"
              f"{mde_s:>7}{strict_s:>8}{conv:>7}{degen:>7}  {harness}")
        extra = []
        if s.get("pass_at_1_converged") is not None:
            extra.append(f"pass@1|conv={s['pass_at_1_converged']*100:.1f}% "
                         f"(n={s.get('n_converged_items')})")
        if s.get("acc_strict") is not None:
            extra.append(f"strict budget={s.get('acc_strict_budget')}")
        if s.get("n_degenerate_eosed"):
            extra.append(f"degen={s['n_degenerate_eosed']} "
                         f"(wall {s.get('degenerate_wall_share', 0) * 100:.0f}%, "
                         f"tok {s.get('degenerate_token_share', 0) * 100:.0f}%)")
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
    # The `conv% >= 90` GATE is WITHDRAWN (AGENTS.md, 2026-08-11) — it was never derived or agreed,
    # conv% is quantized in n, a point estimate against a hard threshold fails 35-45% of the time by
    # chance at a TRUE rate of 0.90, and on cost grounds it is ~10x too lenient. Printing it as
    # "pre-registered" is how a retracted rule keeps getting applied, so the footer now states the
    # ratified reporting rule instead: four separately-interpretable numbers, no composites.
    print("\nREPORTING RULE (AGENTS.md): report these SEPARATELY — no composites.")
    print("  1 capability  — acc/pass@1 + CI, plus the exclusive-solve sets")
    print("  2 edit competence — well-formed / malformed / context-exhaustion rates")
    print("  3 latency     — mean/median/p95 seconds per task")
    print("  4 runaway tax — non-self-terminating RATE and its measured share of wall-clock")
    print("conv% and nonconv kinds are DIAGNOSTICS, not a pass/fail: the conv%>=90 gate is WITHDRAWN.")
    print("strict = THE RANKING KEY at a matched budget: a DNF scores 0 with the denominator INTACT,")
    print("  so a model that DNFs 99 of 100 tasks scores 1%, not 100%. Comparable only at an EQUAL")
    print("  thinking_budget (compare refuses otherwise); the budget is shown in the detail line.")
    print("acc = correctness over generated items (historical meaning), kept so published rows stay")
    print("  comparable. pass@1|conv is a DIAGNOSTIC and must NEVER rank — it conditions on")
    print("  convergence, shrinking the denominator, which is the 99-DNF pathology above.")
    print("'harness' is BROKEN only when the HARNESS failed, not the model.")
    print("degen = self-terminating repetition loops: scored CONVERGED and included in acc, flagged")
    print("for the judge panel; their wall/token share is COST, reported beside capability.")
    if ungated:
        print("\n⚠️  LOW CONVERGENCE (a diagnostic, NOT a gate) — these did not self-terminate often;")
        print("    investigate the mechanism (nonconv kinds above), do NOT rank on pass@1 alone:")
        for s in ungated:
            print(f"   {s['model']} / {s['benchmark']}: conv {s['conv_rate']*100:.0f}% "
                  f"kinds={s.get('nonconv_kinds')}")
    if broken:
        print("\n⛔ HARNESS-BROKEN runs (errors, not model behaviour) — fix and re-run:")
        for s in broken:
            print(f"   {s['model']} / {s['benchmark']}: {s.get('note')}")
    print(f"Full scores -> {generate.results_root()}/scores.json")


def _print_compare_verdict(label, model_a, model_b, r, margin):
    """The delta/CI/verdict block shared by the single-bench and pooled (`--pool`) prints."""
    print(f"\n=== {label}: {model_a}  vs  {model_b}")
    if not r["comparable"]:
        print(f"  NOT COMPARABLE — {r['reason']}")
        return
    d = r["delta"]
    print(f"  matched items: {r['n_items']}   samples: {r['samples']}   axis MDE: ±{r['mde']*100:.0f}pp")
    print(f"  {r['metric']}: {r['a']*100:.1f}% vs {r['b']*100:.1f}%")
    print(f"  delta {d['delta']*100:+.1f}pp   95% CI [{d['lo']*100:+.1f}, {d['hi']*100:+.1f}]pp")
    print(f"  VERDICT: {d['verdict'].upper()}")
    if d["verdict"] == "inconclusive":
        print(f"  (the interval spans 0 and is wider than the ±{margin*100:.0f}pp "
              f"equivalence margin — this is NOT evidence of a tie; it is too little data. "
              f"{r['n_for_margin']} matched items would be needed.)")


def cmd_compare(args):
    """Paired head-to-head between two models on one bench, with a verdict that can be
    'inconclusive'. Refuses any comparison the data cannot support rather than printing a delta.

    `--pool` (M12): one pooled paired verdict across >=2 --benches on acc_strict, instead of one
    compare per bench — see bench/compare.py:pooled_compare for the comparability gate and the
    stratified-bootstrap mechanism.
    """
    from bench import compare as CMP
    models, benches, _ = _resolve(args)
    if len(models) != 2:
        print("compare needs exactly two --models"); return
    tune = getattr(args, "tune", None)
    intersect = getattr(args, "intersect", False)

    if getattr(args, "pool", False):
        if len(benches) < 2:
            print("--pool needs at least two --benches"); return
        r = CMP.pooled_compare(models[0], models[1], benches, margin=args.margin, tune=tune,
                               intersect=intersect)
        _print_compare_verdict(f"POOLED [{', '.join(benches)}]", models[0], models[1], r,
                               args.margin)
        if r["comparable"]:
            print("  per-bench:")
            for b, s in r["per_bench"].items():
                bd = s["delta"]
                print(f"    {b}: n={s['n_items']}  {r['metric']} {s['a']*100:.1f}% vs "
                      f"{s['b']*100:.1f}%  delta {bd['delta']*100:+.1f}pp "
                      f"[{bd['lo']*100:+.1f}, {bd['hi']*100:+.1f}]pp  {bd['verdict']}")
            for w in r.get("warnings", []):
                print(f"  ⚠️  {w}")
        return

    m0 = models[0] if (not tune or "@" in models[0]) else f"{models[0]}@{tune}"
    m1 = models[1] if (not tune or "@" in models[1]) else f"{models[1]}@{tune}"
    for b in benches:
        r = CMP.compare(m0, m1, b, margin=args.margin, intersect=intersect)
        _print_compare_verdict(b, m0, m1, r, args.margin)
        if not r["comparable"]:
            continue
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


def build_parser():
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
    sp.add_argument("--depth-tokens", dest="depth_tokens", type=int, default=None,
                    help="coding-at-depth (D9): embed each item at the end of ~N tokens of "
                         "deterministic repo context. Provenance-tracked; requires --tune")
    sp.add_argument("--presence-penalty", dest="presence_penalty", type=float, default=None,
                    help="override presence_penalty (provenance-tracked). NOTE: any nonzero penalty "
                         "also DISABLES suffix decoding for the request, so it changes the serving "
                         "path as well as the sampling distribution")
    sp.add_argument("--repetition-penalty", dest="repetition_penalty", type=float, default=None,
                    help="override repetition_penalty (provenance-tracked). Same serving-path caveat "
                         "as --presence-penalty")
    sp.add_argument("--reasoning-effort", dest="reasoning_effort",
                    choices=["xhigh", "medium", "low"], default=None,
                    help="template effort knob (Qwen3.8-27B family; the template default is "
                         "xhigh, and absent means that default). Provenance-tracked into the "
                         "fingerprint's sampling slice; REQUIRES --tune (e.g. t0.6-effmed) "
                         "so effort rows never pool with the template-default corpus (M24)")
    sp.add_argument("--ids", default=None,
                    help="restrict to NAMED items, per bench: 'ifeval=2849:279,humanevalplus=HumanEval/94'. "
                         "Colon-separated (comma already separates bench pairs, and ids can contain "
                         "commas). Ids are drawn from the seeded shuffle's prefix, so they must be "
                         "within --limit; an unknown id fails LOUDLY rather than running a subset. Use "
                         "this for a targeted probe that varies ONE knob on the SAME items -- which "
                         "selection-by-count cannot express.")
    sp.add_argument("--thinking-budget", dest="thinking_budget", type=int, default=None,
                    help="override thinking_budget for all models (default: config value — "
                         "16384 Gemma / 49152 Qwen). Lower it to bound eval time.")
    sp.add_argument("--auto-restart-on-loop", dest="auto_restart_on_loop", action="store_true",
                    help="on a looped/truncated item, restart the router + re-probe once; "
                         "classify recovered (stale router) vs loop_persisted (genuine quant loop)")
    sp.add_argument("--sampling-profile", dest="sampling_profile",
                    choices=model_params.profile_names(), required=True,
                    help="REQUIRED (O36): the old default `production` has drifted from what we "
                         "ship and silently measured the wrong serving path. deployed = registry "
                         "generation_defaults, the profile for ALL new axes; production = the "
                         "frozen legacy table (old rows only); "
                         "official = each family's published recommended sampling (quality eval); "
                         "coding = converging sampling + a thinking_budget large enough to not "
                         "truncate hard-problem reasoning")
    sp.add_argument("--probe-timeout", dest="probe_timeout", type=int, default=None,
                    help="per-item HTTP timeout (s). DEFAULT IS DERIVED (C28): thinking_budget / "
                         "the model's measured slow-tail decode rate x safety, so the bound always "
                         "clears full-budget generation. A bound BELOW it is an active defect - the "
                         "client abandons, the worker does not cancel, and the orphan starves the "
                         "next item into a false DNF (M23 lost a whole leg that way). Pass a value "
                         "only to override the derivation.")
    sp.add_argument("--samples", type=int, default=1,
                    help="draws per item (k). Each draw gets its own seed — WITHOUT that the "
                         "server returns byte-identical text and reliability reads as perfect. "
                         "k buys RELIABILITY, not power: at N=15, k=1->5 shrinks the SD only "
                         "12.7->10.8pp, while 5x the items gives -55%%. Use k=2-3 and spend the "
                         "rest on items.")
    sp.add_argument("--seed-base", dest="seed_base", type=int, default=0,
                    help="shift every draw's seed (for an independent replication of a run that "
                         "already exists on disk)")
    sp.add_argument("--clean-stale", dest="clean_stale", action="store_true",
                    help="delete + regenerate any existing results whose recorded config "
                         "(sampling/profile/KV) differs from this run, instead of resuming on "
                         "top of them (which would mix provenance). Default: warn + keep.")
    sp.add_argument("--tune", type=generate.validate_tune, default=None,
                    help="short label for a non-deployed config, e.g. kv4, t0.3, suffixon, "
                         "cap16, or a +-composed kv4+t0.3. Encoded in filenames as "
                         "<bench>.<tune>.jsonl and stamped as manifest['tune']; omit for the "
                         "deployed tune (today's <bench>.jsonl, unchanged). Lowercase "
                         "[a-z0-9._-]+ per +-separated component, no leading/trailing dot.")

    sp = sub.add_parser("grade"); common(sp); sp.set_defaults(func=cmd_grade)
    sp.add_argument("--tune", type=generate.validate_tune, default=None,
                    help="grade the run stamped with this tune label instead of the deployed "
                         "baseline (see `generate --tune`); reads/writes <bench>.<tune>.*.")
    sp = sub.add_parser("status"); common(sp); sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("compare"); common(sp); sp.set_defaults(func=cmd_compare)
    sp.add_argument("--intersect", action="store_true",
                    help="if the item sets differ, pair on the SHARED items instead of refusing. "
                         "For nested sets (one run a subset of another) this recovers a genuine "
                         "matched comparison; the output names how many items were dropped.")
    sp.add_argument("--margin", type=float, default=0.05,
                    help="equivalence margin for the TOST verdict (default 5pp)")
    sp.add_argument("--tune", type=generate.validate_tune, default=None,
                    help="compare the tune-stamped rows for BOTH models (see `generate --tune`); "
                         "same as suffixing '@tune' onto each --models entry, left alone if a "
                         "model already carries its own '@tune'.")
    sp.add_argument("--pool", action="store_true",
                    help="M12 pooled cross-bench compare (needs >=2 --benches): runs the same "
                         "per-bench comparability gate as the default per-bench compare, then "
                         "pools paired acc_strict outcomes across benches into ONE verdict via a "
                         "bootstrap STRATIFIED by bench (every draw keeps each bench's own item "
                         "count fixed). Any bench refusing, or a mismatched (thinking_budget, "
                         "max_tokens) ACROSS benches, refuses the whole pooled compare.")

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

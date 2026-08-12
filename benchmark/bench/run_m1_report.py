#!/usr/bin/env python3
"""Aggregate the M1 agentic head-to-head into a campaign-results row.

M1 runs as one aider invocation per (model, language), so a model's result is spread across
several run dirs (`<timestamp>--m1-<tag>-<lang>`). This collects them, aggregates with aider's own
pass-rate semantics, and prints the reliability-bearing row plus the paired verdict.

WHY A DEDICATED REPORTER rather than reading aider's console summary:
  * aider prints two numbers; the operational signals that decide a daily driver (malformed edits,
    output-limit hits, per-case duration, timeouts) live only in the per-case JSON.
  * the pass rate must never be printed without its resolution — n=110 is +-11.9pp, and the
    campaign's history is of 5-to-34-case rows being read as rankings.
  * the two arms MUST be compared on matched exercises. aider's `--num-tests` is an unseeded
    random sample, so matching is not automatic; this reports the intersection size and refuses to
    call a winner when the sets differ.

Usage (run where the aider benchmark dir lives, i.e. the worker box):
  python -m bench.run_m1_report --bench-dir ~/Documents/ws/aider/benchmark/tmp.benchmarks \\
      --arm ornith:Ornith-1.0-35B-mlx-uniform-4bit --arm distill:Qwen3.6-27B-Opus-Distill-OptiQ-4bit \\
      --langs python,javascript,go,rust,java [--markdown]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bench import aider_adapter, stats  # noqa: E402


def convergence_from_router_log(path, model, thinking_budget, max_tokens, since=None):
    """Per-CALL convergence for the agentic axis, read from the router log.

    The convergence discipline was only ever applied to single-shot benches, but a runaway turn is
    worse in an agentic loop: it costs wall-clock AND poisons the next turn's context. Observed on
    the first Ornith wave — one call returned `completion=102401`, i.e. the model produced its whole
    102,400-token budget and was truncated, burning 14.1 minutes on one turn.

    Attribution to a specific exercise is not reliable (the log has no case id), so this reports
    RUN-LEVEL counts, which is enough to say "N of M turns failed to self-terminate":
      budget_hit  completion >= thinking_budget  (thinking filled its cap, then answered)
      runaway     completion >= max_tokens       (hard truncation; finish_reason would be length)
    """
    import re
    calls, budget_hits, runaways, tokens = 0, 0, 0, []
    pat = re.compile(r"model=(\S+).*?\| completion=(\d+)")
    # `since` ("YYYY-MM-DD HH:MM:SS") excludes calls that predate this run. Without it the counts
    # silently absorb smoke/aborted-run traffic against the same model, which would understate the
    # non-convergence RATE by inflating the denominator with short warm-up calls.
    try:
        with open(os.path.expanduser(path), errors="replace") as f:
            for line in f:
                if "/v1/chat/completions 200" not in line:
                    continue
                if since and line[:len(since)] < since:
                    continue
                m = pat.search(line)
                if not m or m.group(1) != model:
                    continue
                ct = int(m.group(2))
                calls += 1
                tokens.append(ct)
                if ct >= max_tokens:
                    runaways += 1
                elif ct >= thinking_budget:
                    budget_hits += 1
    except OSError:
        return None
    if not calls:
        return None
    tokens.sort()
    return {"calls": calls, "budget_hits": budget_hits, "runaways": runaways,
            "nonconverged_rate": round((budget_hits + runaways) / calls, 4),
            "median_completion": tokens[len(tokens) // 2], "max_completion": tokens[-1]}


def collect_arm(bench_dir, tag, langs):
    """All cases for one arm, keyed by exercise name so arms can be paired item-by-item."""
    cases, by_lang = {}, {}
    for lang in langs:
        got = aider_adapter.collect_case_results(bench_dir, run_name=f"m1-{tag}-{lang}")
        by_lang[lang] = len(got)
        for c in got:
            name = c.get("testcase")
            if name:
                cases[f"{lang}/{name}"] = c
    return cases, by_lang


def per_item_scores(cases):
    """{item: [1.0|0.0]} using aider's credit rule (last attempt passed)."""
    return {k: [1.0 if c.get("passed") else 0.0] for k, c in cases.items()}


def summarize(name, cases):
    agg = aider_adapter.aggregate_cases(list(cases.values()))
    rel = aider_adapter.reliability_summary(agg)
    per = per_item_scores(cases)
    n = len(per)
    out = {"model": name, "n": n, "by_lang": None, "agg": agg, "rel": rel}
    if n:
        boot = stats.cluster_bootstrap(per, iters=4000, seed=0)
        out["acc"] = stats.pass_at_1(per)
        out["ci95"] = (boot["lo"], boot["hi"])
        out["mde"] = stats.mde(n)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench-dir", required=True)
    ap.add_argument("--arm", action="append", required=True,
                    help="tag:served-model  (repeatable; exactly two for a paired verdict)")
    ap.add_argument("--langs", default="python,javascript,go,rust,java")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--router-log", default=None,
                    help="mlx-serve log; adds per-CALL convergence (runaway/budget-hit counts)")
    ap.add_argument("--thinking-budget", type=int, default=81920)
    ap.add_argument("--max-tokens", type=int, default=102400)
    ap.add_argument("--since", default=None,
                    help='ignore router-log calls before this "YYYY-MM-DD HH:MM:SS" (exclude smoke)')
    a = ap.parse_args(argv)

    langs = [x.strip() for x in a.langs.split(",") if x.strip()]
    arms = []
    for spec in a.arm:
        tag, _, model = spec.partition(":")
        cases, by_lang = collect_arm(os.path.expanduser(a.bench_dir), tag, langs)
        s = summarize(model or tag, cases)
        s["tag"], s["by_lang"], s["cases"] = tag, by_lang, cases
        if a.router_log:
            s["conv"] = convergence_from_router_log(a.router_log, s["model"],
                                                    a.thinking_budget, a.max_tokens, a.since)
        arms.append(s)

    for s in arms:
        print(f"\n=== {s['model']}  (tag {s['tag']})")
        print(f"  cases: {s['n']}  per-language: {s['by_lang']}")
        if not s["n"]:
            print("  no results yet")
            continue
        agg, rel = s["agg"], s["rel"]
        pr1, pr2 = agg.get("pass_rate_1"), agg.get("pass_rate_final") or agg.get("pass_rate_2")
        print(f"  pass_rate_1={pr1}  pass_rate_final={pr2}")
        print(f"  acc={s['acc']*100:.1f}%  95% CI [{s['ci95'][0]*100:.0f},{s['ci95'][1]*100:.0f}]  "
              f"MDE ±{s['mde']*100:.1f}pp")
        print(f"  well_formed={agg.get('percent_cases_well_formed')}  "
              f"malformed={agg.get('num_malformed_responses')}  "
              f"output_limit_hits={agg.get('output_limit_hits')}  "
              f"test_timeouts={agg.get('test_timeouts')}  crashed={agg.get('n_crashed')}")
        print(f"  time-to-success: {rel.get('expected_s')}s  "
              f"({rel.get('successes_per_hour')}/h)  thin_evidence={rel.get('thin_evidence')}")
        c = s.get("conv")
        if c:
            print(f"  TURN CONVERGENCE: {c['calls']} calls, {c['runaways']} runaway (hit "
                  f"max_tokens), {c['budget_hits']} budget-hit -> nonconverged "
                  f"{c['nonconverged_rate']*100:.1f}% of turns; median {c['median_completion']} "
                  f"max {c['max_completion']} completion tokens")

    if len(arms) == 2 and all(s["n"] for s in arms):
        a0, a1 = arms
        shared = sorted(set(a0["cases"]) & set(a1["cases"]))
        only0 = sorted(set(a0["cases"]) - set(a1["cases"]))
        only1 = sorted(set(a1["cases"]) - set(a0["cases"]))
        print(f"\n=== PAIRED VERDICT on {len(shared)} matched exercises")
        if only0 or only1:
            print(f"  ⚠ unmatched: {len(only0)} only-{a0['tag']}, {len(only1)} only-{a1['tag']} "
                  f"— pairing on the intersection; aider's --num-tests is an unseeded random "
                  f"sample, so an unmatched pair means the pinning did not hold")
        if not shared:
            print("  NOT COMPARABLE — no shared exercises")
        else:
            pa = {k: v for k, v in per_item_scores(a0["cases"]).items() if k in shared}
            pb = {k: v for k, v in per_item_scores(a1["cases"]).items() if k in shared}
            d = stats.paired_delta(pa, pb, iters=8000, seed=0)
            print(f"  {a0['model']}: {stats.pass_at_1(pa)*100:.1f}%")
            print(f"  {a1['model']}: {stats.pass_at_1(pb)*100:.1f}%")
            print(f"  delta {d['delta']*100:+.1f}pp  CI [{d['lo']*100:+.1f},{d['hi']*100:+.1f}]pp"
                  f"  MDE ±{stats.mde(len(shared))*100:.1f}pp")
            print(f"  VERDICT: {d['verdict'].upper()}")
            if d["verdict"] == "inconclusive":
                print(f"  (interval spans 0 and exceeds the equivalence margin — too little data, "
                      f"NOT evidence of a tie; {stats.n_for(0.05)} matched cases would resolve 5pp)")

    if a.markdown:
        print("\n| model | n | pass_rate_final | acc | 95% CI | MDE | well-formed | out-limit | s/success |")
        print("|---|---|---|---|---|---|---|---|---|")
        for s in arms:
            if not s["n"]:
                continue
            agg, rel = s["agg"], s["rel"]
            print(f"| {s['model']} | {s['n']} | "
                  f"{agg.get('pass_rate_final') or agg.get('pass_rate_2')} | "
                  f"{s['acc']*100:.1f}% | [{s['ci95'][0]*100:.0f},{s['ci95'][1]*100:.0f}] | "
                  f"±{s['mde']*100:.1f}pp | {agg.get('percent_cases_well_formed')} | "
                  f"{agg.get('output_limit_hits')} | {rel.get('expected_s')} |")

    if a.json_out:
        with open(a.json_out, "w") as f:
            json.dump([{k: v for k, v in s.items() if k != "cases"} for s in arms], f, indent=2)
        print(f"\nwrote {a.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Per-model x per-benchmark SCOREBOARD with a verdict per user-scenario role.

WHY THIS EXISTS. `campaign-results.md` is a narrative record — accurate, but organised by discovery
order, so "how did model X do on everything, and is it good enough for MY use case?" takes a dozen
greps. And `compare` answers a different question ("is A better than B?"), returning verdicts like
`equivalent` that say nothing about whether either model is USABLE.

This reads the persisted per-item rows directly and emits one row per (model, bench), then a per-model
coverage verdict against each stated goal — REASONING, CODING, DAILY DRIVER.

Built from the jsonl rows rather than scores.json, because scores.json only holds whatever the LAST
`grade` invocation covered, so a scoreboard built from it silently drops every model not in that call.

  PYTHONPATH=benchmark .venv-bench/bin/python benchmark/m1/scoreboard.py [--md]
"""
import argparse
import json
from pathlib import Path

from bench import convergence, paths, traces

# Which benchmarks speak to which stated goal. A bench may serve more than one role.
ROLES = {
    "reasoning": ["aime", "math500", "gpqa"],
    "coding": ["humanevalplus", "mbppplus", "livecodebench", "aider"],
    "daily": ["ifeval", "bfcl"],
}
# Below this n, MDE exceeds ~32pp and a number cannot support a verdict.
MIN_N_FOR_VERDICT = 10


def _rows(path: Path) -> list:
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def collect() -> dict:
    root = paths.default_results_root()
    out = {}
    for f in sorted(root.glob("*/*.jsonl")):
        bench = f.stem.split(".")[0]              # livecodebench.t03 -> livecodebench
        if bench.endswith("_samples"):
            continue                             # multi-draw sidecars, not a separate axis
        rows = _rows(f)
        live = [r for r in rows if not r.get("error")]
        if not live:
            continue
        # Convergence is only DEFINED for rows that expose per-turn generation. The aider agentic
        # rows carry converged=None on purpose (aider gives a per-CASE view across turns, so there is
        # no per-turn finish_reason/completion_tokens to judge). Counting None as converged — which
        # `is not False` does — printed a fabricated conv 100% for both aider arms.
        det = [r for r in live if convergence.is_converged(r) is not None]
        conv = [r for r in det if convergence.is_converged(r) is not False]
        degen = [r for r in live if traces.is_degenerate(r)]
        tw = sum(r.get("wall_s") or 0 for r in live) or 1
        budgets = {r.get("thinking_budget") for r in live if r.get("thinking_budget")}
        # acc / acc_strict come from the per-pair score file that `grade_all` writes beside the rows.
        # NOT from scores.json, which holds only the last grade call and so silently drops models.
        # An UNGRADED pair reads None -> "ungraded" in the table, never a blank or a zero: the whole
        # point of this scoreboard is that an unmeasured combination cannot be mistaken for a pass.
        sp = f.with_suffix(".score.json")
        sc = {}
        if sp.exists():
            try:
                sc = json.loads(sp.read_text())
            except (json.JSONDecodeError, OSError):
                sc = {}
        rec = {"n": len(live), "errors": len(rows) - len(live),
               # None => UNDETERMINABLE, rendered "n/a". Never 100.
               "conv_pct": (100 * len(conv) / len(det)) if det else None,
               "degen": len(degen),
               "degen_wall_pct": 100 * sum(r.get("wall_s") or 0 for r in degen) / tw,
               "budget": sorted(budgets)[0] if len(budgets) == 1 else None,
               "acc": sc.get("acc"), "acc_strict": sc.get("acc_strict")}
        m = out.setdefault(f.parent.name, {})
        prev = m.get(bench)
        if prev is None or rec["n"] > prev["n"]:   # keep the largest n across variants
            m[bench] = rec
    return out


def verdict(benches: dict, role: str) -> str:
    """A coverage verdict, or an explicit reason one cannot be given. Never a silent blank."""
    have = [(b, benches[b]) for b in ROLES[role] if b in benches]
    if not have:
        return "NOT MEASURED"
    parts = [f"{len(have)}/{len(ROLES[role])} axes"]
    thin = [b for b, r in have if r["n"] < MIN_N_FOR_VERDICT]
    if thin:
        parts.append(f"UNDERPOWERED on {','.join(thin)}")
    missing = [b for b in ROLES[role] if b not in benches]
    if missing:
        parts.append(f"missing {','.join(missing)}")
    convs = [r["conv_pct"] for _, r in have if r["conv_pct"] is not None]
    worst = min(convs) if convs else None
    if worst is not None and worst < 90:
        parts.append(f"conv {worst:.0f}% — investigate mechanism")
    return "; ".join(parts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Per-model scoreboard with role coverage verdicts.")
    ap.add_argument("--md", action="store_true", help="emit markdown")
    args = ap.parse_args(argv)
    data = collect()
    hdr = ("model", "bench", "n", "acc", "strict", "conv%", "degen", "degenWall%", "budget")
    if args.md:
        print("| " + " | ".join(hdr) + " |")
        print("|" + "---|" * len(hdr))
    else:
        print("%-40s %-15s %5s %7s %7s %6s %6s %11s %8s" % hdr)
    for model in sorted(data):
        for bench in sorted(data[model]):
            r = data[model][bench]
            # "ungraded" rather than a blank: the ranking key being absent is information.
            acc_s = "ungraded" if r["acc"] is None else f"{r['acc'] * 100:.1f}%"
            st_s = "ungraded" if r["acc_strict"] is None else f"{r['acc_strict'] * 100:.1f}%"
            v = (model, bench, r["n"], acc_s, st_s, ("n/a" if r["conv_pct"] is None else f"{r['conv_pct']:.0f}"), r["degen"] or "-",
                 f"{r['degen_wall_pct']:.0f}" if r["degen"] else "-", r["budget"] or "-")
            print(("| " + " | ".join(str(x) for x in v) + " |") if args.md
                  else "%-40s %-15s %5s %7s %7s %6s %6s %11s %8s" % v)
    print("\n=== ROLE COVERAGE (what is measured, what is missing) ===")
    for model in sorted(data):
        print(f"\n{model}")
        for role in ROLES:
            print(f"   {role:10} {verdict(data[model], role)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

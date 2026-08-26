"""Per-model x per-benchmark SCOREBOARD with a verdict per user-scenario role.

WHY THIS EXISTS. `campaign-results.md` is a narrative record — accurate, but organised by discovery
order, so "how did model X do on everything, and is it good enough for MY use case?" takes a dozen
greps. And `compare` answers a different question ("is A better than B?"), returning verdicts like
`equivalent` that say nothing about whether either model is USABLE.

This walks the persisted per-item rows and emits one row per (model, bench), then a per-model
coverage verdict against each stated goal — REASONING, CODING, DAILY DRIVER.

It DISCOVERS pairs from the jsonl rows rather than from scores.json, because scores.json only holds
whatever the LAST `grade` invocation covered, so a scoreboard built from it silently drops every model
not in that call. But every GRADED NUMBER — `acc`, `acc_strict`, `conv%`, `degenEosedWall%` — is read
from the per-pair `<bench>.score.json` beside those rows, never recomputed here. This module is a
PRESENTER; `grade` is the one place metrics are defined. Recomputing convergence here is exactly how
the scoresheet came to publish ifeval conv 99 / 99 for the two winners after `grade` had corrected
them to 95 / 93 (see `collect`).

  PYTHONPATH=benchmark .venv-bench/bin/python benchmark/m1/scoreboard.py [--md]
"""
import argparse
import json
from pathlib import Path

from bench import convergence, paths, traces

# Which benchmarks speak to which stated goal. A bench may serve more than one role.
# `opencode` is the primary agentic harness for "coding" (opencode is what this stack ships;
# see AGENTS.md client integrations table).
ROLES = {
    "reasoning": ["aime", "math500", "gpqa"],
    "coding": ["humanevalplus", "mbppplus", "livecodebench", "opencode"],
    "daily": ["ifeval", "bfcl"],
}
# Benches kept on the sheet (rows are never dropped) but demoted OUT of the role's headline
# coverage verdict. `aider` was RETIRED as a harness 2026-08-16 (`AGENTS.md` client integrations
# table: "opencode is the primary agentic harness") -- its 110 rows stay for reference/diagnosis,
# but they must not count toward, or be mistaken for, the "coding" role's verdict.
DIAGNOSTIC_ROLES = {
    "coding": ["aider"],
}
# Below this n, MDE exceeds ~32pp and a number cannot support a verdict.
MIN_N_FOR_VERDICT = 10


def _kv_label(kv: dict) -> str | None:
    """Compact KV-cache provenance: 'TQ4' (turboquant 4-bit), 'uniform4', 'fp16' (kv_bits 0).
    None (-> 'n/a') when the manifest predates kv provenance — unknown is never rendered as fp16.
    The corpus genuinely mixes all three (54 TQ4 / 11 uniform4 / 25 fp16 pairs on 2026-08-26), so a
    cell without this column silently pools across a lossy-lever change (operator 2026-08-26)."""
    bits = kv.get("kv_bits")
    if bits is None:
        return None
    if bits == 0:
        return "fp16"
    scheme = kv.get("kv_quant_scheme") or "kv"
    return ("TQ" if scheme == "turboquant" else scheme) + str(bits)


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
        # ⚠️ conv% IS READ FROM THE SCORE FILE, NEVER RE-DERIVED HERE. This module used to recompute
        # it from the rows, and that silently UNDID the resolved-thinking-budget correction: the
        # server clamps thinking_budget to 0.8*(max_kv_cache_size - prompt) without logging it, so
        # `grade._rows` annotates `resolved_thinking_budget` from the run MANIFEST — and the rows on
        # disk carry no such field (0 of 541 and 0 of 148 on the two ifeval runs). Re-deriving from
        # rows alone therefore judged against the DECLARED 81,920 and published ifeval conv 99 / 99
        # for `Ornith-1.0-35B-mlx-uniform-4bit` and `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` while their
        # score files said 0.9464 / 0.9324 (95 / 93) — the scoresheet printed the left-hand side of
        # its own retraction (AGENTS.md, measurement discipline).
        #
        # WHY THIS SEAM AND NOT PERSISTING THE FIELD IN THE ROWS: a row-level field only helps rows
        # generated from here on, so the 689 already-measured ifeval rows would stay wrong until
        # re-generated (hours of single-worker time for a number that is a FREE re-grade). And a
        # second copy of the clamp arithmetic is a second place to forget the next correction —
        # exactly this defect. `grade` is the ONE place metrics are defined; this module is a
        # PRESENTER of what was graded. Cost: an ungraded pair reads `n/a` instead of a number
        # nobody audited, which is the convention `acc`/`acc_strict` already follow. Fixing a cell
        # means running `grade` (zero worker time), not recomputing here.
        # KV provenance comes from THIS file's manifest, never the registry: the registry is
        # current state, the manifest records what the run was actually served with.
        mp = f.with_name(f.stem + ".manifest.json")
        kv_label = None
        if mp.exists():
            try:
                kv_label = _kv_label(json.loads(mp.read_text()).get("kv") or {})
            except (json.JSONDecodeError, OSError):
                kv_label = None
        conv_rate = sc.get("conv_rate")
        # Convergence is only DEFINED for rows that expose per-turn generation. The aider agentic
        # rows carry converged=None on purpose (aider gives a per-CASE view across turns, so there is
        # no per-turn finish_reason/completion_tokens to judge), and `aider_rows` writes no
        # `conv_rate` — so those cells stay `n/a` rather than the fabricated 100% they once printed.
        # `det` is used ONLY as the denominator for the staleness check below: determinability does
        # not depend on the budget, so it is safe to derive here; the VERDICT is not.
        det = [r for r in live if convergence.is_converged(r) is not None]
        # STALE-GRADE detector — the one cost of reading the graded number. A resumed run appends
        # rows, and the score file then predates them. `loop_ids` is the exact non-converged set the
        # grade covered and `conv_rate` is stored at full precision, so (1 - conv_rate) * today's
        # denominator must reproduce its size EXACTLY (to float noise); verified 2026-08-16 to hold
        # for all 54 pairs in the corpus that carry a graded `conv_rate` (0 flagged). A mismatch is
        # MARKED (`*`), so a stale cell says so instead of reading as current.
        loop_ids = sc.get("loop_ids")
        expect_loops = None if conv_rate is None else (1 - conv_rate) * len(det)
        rec = {"n": len(live), "errors": len(rows) - len(live),
               # None => UNGRADED/UNDETERMINABLE, rendered "n/a". Never 100.
               "conv_pct": None if conv_rate is None else 100 * conv_rate,
               "conv_stale": bool(expect_loops is not None and loop_ids is not None
                                  and abs(expect_loops - len(loop_ids)) > 1e-6),
               # TWO degeneracy definitions are in use and they differ by up to ~10x on the SAME
               # rows, so each carries its definition in its NAME (see the legend in main()):
               #   degen_all*   — EVERY row whose trace shows a verbatim loop, however it ended.
               #   degen_eosed* — `grade`'s persisted `degenerate_wall_share`: the SELF-TERMINATING
               #                  (EOS'd) degenerate rows only, i.e. the loops the convergence
               #                  formula scores as CONVERGED. Read, not recomputed — it depends on
               #                  the resolved budget, for the reasons above.
               "degen_all": len(degen),
               "degen_all_wall_pct": 100 * sum(r.get("wall_s") or 0 for r in degen) / tw,
               "degen_eosed_wall_pct": (None if sc.get("degenerate_wall_share") is None
                                        else 100 * sc["degenerate_wall_share"]),
               "budget": sorted(budgets)[0] if len(budgets) == 1 else None,
               "acc": sc.get("acc"), "acc_strict": sc.get("acc_strict"),
               "kv": kv_label}
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
    hdr = ("model", "bench", "n", "acc", "strict", "conv%", "degenAll", "degenAllWall%",
           "degenEosedWall%", "budget", "kv")
    fmt = "%-40s %-15s %5s %7s %7s %6s %8s %13s %15s %8s %8s"
    if args.md:
        print("| " + " | ".join(hdr) + " |")
        print("|" + "---|" * len(hdr))
    else:
        print(fmt % hdr)
    # Flat set of benches demoted to diagnostic status under ANY role, so the main sheet marks
    # them inline rather than silently keeping them indistinguishable from headline rows.
    diag_benches = {b for benches in DIAGNOSTIC_ROLES.values() for b in benches}
    stale = False
    for model in sorted(data):
        for bench in sorted(data[model]):
            r = data[model][bench]
            # "ungraded" rather than a blank: the ranking key being absent is information.
            acc_s = "ungraded" if r["acc"] is None else f"{r['acc'] * 100:.1f}%"
            st_s = "ungraded" if r["acc_strict"] is None else f"{r['acc_strict'] * 100:.1f}%"
            # conv% is the GRADED number (see collect). "*" = the grade predates the rows on disk.
            conv_s = "n/a" if r["conv_pct"] is None else f"{r['conv_pct']:.0f}"
            if r["conv_stale"]:
                conv_s += "*"
                stale = True
            bench_s = f"{bench} [diag]" if bench in diag_benches else bench
            v = (model, bench_s, r["n"], acc_s, st_s, conv_s, r["degen_all"] or "-",
                 f"{r['degen_all_wall_pct']:.0f}" if r["degen_all"] else "-",
                 "n/a" if r["degen_eosed_wall_pct"] is None else f"{r['degen_eosed_wall_pct']:.0f}",
                 r["budget"] or "-",
                 r["kv"] or "n/a")
            print(("| " + " | ".join(str(x) for x in v) + " |") if args.md else fmt % v)
    # The legend TRAVELS WITH THE SHEET, because the sheet gets pasted into campaign-results.md and a
    # cell is read on its header. One name for both degeneracy measures is how a 63%-vs-0% ambiguity
    # spreads (`Ornith-1.0-35B-mlx-uniform-4bit` mbppplus).
    print("\nconv% = the GRADED convergence rate read from <bench>.score.json (judged against the "
          "SERVER-RESOLVED thinking budget); n/a = ungraded or undeterminable. "
          "degenAllWall% = wall-clock share of EVERY row whose trace shows a verbatim loop, however "
          "it ended (derived here). degenEosedWall% = the persisted `degenerate_wall_share`: the "
          "same share over the SELF-TERMINATING (EOS'd) degenerate rows ONLY — the loops the "
          "convergence formula counts as CONVERGED. The two are NOT interchangeable. "
          "kv = KV-cache quantization the run was SERVED with, from the run manifest: scheme+bits "
          "(TQ = turboquant, uniform = mlx uniform affine), fp16 = unquantized (kv_bits 0), "
          "n/a = pre-provenance run. Rows differing in kv are different serving paths — do not pool.")
    if stale:
        print("* = the score file was graded over a different row count than is on disk now "
              "(a resumed run). RE-GRADE (zero worker time); do not read the cell as current.")
    print("\n=== ROLE COVERAGE (what is measured, what is missing) ===")
    print("[diag] rows are shown for reference but excluded from the role verdict below "
          "(DIAGNOSTIC_ROLES) -- currently `aider`, retired as a harness 2026-08-16.")
    for model in sorted(data):
        print(f"\n{model}")
        for role in ROLES:
            print(f"   {role:10} {verdict(data[model], role)}")
        for role, benches in DIAGNOSTIC_ROLES.items():
            have = [b for b in benches if b in data[model]]
            if not have:
                continue
            cells = []
            for b in have:
                r = data[model][b]
                acc_s = "ungraded" if r["acc"] is None else f"{r['acc'] * 100:.1f}%"
                st_s = "ungraded" if r["acc_strict"] is None else f"{r['acc_strict'] * 100:.1f}%"
                cells.append(f"{b} (n={r['n']}, acc={acc_s}, strict={st_s})")
            print(f"   {role + ' [diag]':10} " + "; ".join(cells))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

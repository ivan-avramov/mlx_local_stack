#!/usr/bin/env python3
"""M54: cross-arm comparison report for AgentBench OS (`run_agentbench_os.py`) results.

Input: N arms, each a `--rows MODEL=PATH` (full registry name) pointing at a rows.jsonl file
produced by `run_agentbench_os.py`; the sibling `<stem>.manifest.json`
(`run_agentbench_os.manifest_path_for`) is read automatically, or overridden with
`--manifest MODEL=PATH`.

COMPARABILITY GATE (AGENTS.md "APPLES-TO-APPLES IS MANDATORY"): before computing ANY statistic,
every arm's manifest is checked against the first arm's for corpus sha, exclusions sha,
round_limit, exec_timeout_s, harness git stack_head, draft_kind state, sampling profile, and
shell_mode (13th round: a non-interactive and an interactive/pty shell are not the same
measurement -- a syntax error in a bash_action ends the episode differently under each). ANY
mismatch REFUSES the whole run (prints every mismatch, writes nothing) -- these are the axes
that silently turn a model comparison into a (model x harness-config) composite.
`llm_timeout_s` is explicitly EXEMPTED (it is a DERIVED number that legitimately drifts as more
rows accumulate, same reasoning as run_agentbench_os's own resume-identity check) -- a
difference there is recorded and printed, never refused on.

C125 seed_base (manifest AND rows): arms must agree on the effective `runtime.seed_base` (an ABSENT
key = a pre-flag manifest = base 0; a present non-int/negative/bool value refuses), and within each
arm every row's `seed_base` (absent = 0) must equal that arm's manifest base and any row
`sampler_seed` must equal `rowschema.sample_seed(id, 0, base=<base>)`.

Per arm: n, graded_n (setup_error excluded from the denominator, same convention as
`run_agentbench_os.summarize`), acc (capability ceiling -- raw `passed`, NOT gated by
convergence), acc_strict@<thinking_budget> (passed AND converged -- the project's RANKING
metric), conv_rate, nonconv_kind_counts, an outcome breakdown (solved/failed_tests/turn_cap from
`outcome`, plus the separate exec_timeout/shell_died/setup_error/harness_error ROW FLAGS, which
are not mutually exclusive with `outcome`), completion-token and wall_total_s distributions
(mean/median/p90/max), and a per-group pass rate explicitly labelled DIAGNOSTIC ONLY (AGENTS.md:
never a ranking input).

Pairwise, for every pair on the INTERSECTION of each arm's GRADED ids (ids present on only one
side are named, never silently dropped): a paired acc_strict delta with its 95% cluster-bootstrap
CI and TOST +-5pp equivalence verdict (`stats.paired_delta`, items are the clusters, k=1 -- one
draw per item, as every AgentBench-OS row is), an exact McNemar p on the discordant pairs
(`stats.mcnemar_exact`), the exclusive-solve sets (same passed-AND-converged definition as
acc_strict, so the McNemar b/c counts are exactly the two sets' sizes), the nominal MDE for the
intersection n (`stats.mde`), and a Holm correction applied across the WHOLE pairwise family's
McNemar p-values (`stats.holm`) -- the family is every comparable pair in this one report run,
declared up front, per `stats.holm`'s own discipline.

NEVER RANKS ON TOKENS OR WALL-CLOCK (AGENTS.md: `successes_per_hour` is refuted; no composite
metrics) -- they are reported as plain distributions. The four numbers the project reports head
the output: capability ceiling (+ exclusive-solve sets), edit/agent competence (acc_strict),
latency per task (wall_total_s), and the runaway tax (turn_cap + exec_timeout share of n, and
their share of total wall-clock).

Usage:
  cd benchmark && uv run python -m bench.agentbench_compare \\
      --rows <full-registry-name>=results/<model>/agentbench_os.v1.jsonl \\
      --rows <full-registry-name>=results/<model>/agentbench_os.v1.jsonl \\
      --out results/agentbench_os_compare.md
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from . import rowschema
from . import run_agentbench_os as R
from . import stats

# ---- the comparability gate: (manifest key path, human label). stack_head lives at the
# top-level `git` block; everything else lives in `runtime` (see run_agentbench_os.run_generate's
# `runtime` dict literal and provenance.gather/build_manifest).
_GATE_FIELDS = (
    (("runtime", "corpus_sha256"), "corpus sha"),
    (("runtime", "exclusions_sha256"), "exclusions sha"),
    (("runtime", "round_limit"), "round_limit"),
    (("runtime", "exec_timeout_s"), "exec_timeout_s"),
    (("git", "stack_head"), "harness git stack_head"),
    (("runtime", "draft_kind"), "draft_kind state"),
    (("runtime", "sampling_profile"), "sampling profile"),
    # 13th round (fidelity): a non-interactive (`docker exec -i`) and an interactive (pty,
    # `docker exec -it`) shell are not the same measurement -- a syntax error in a bash_action
    # ends the episode as shell_died under one and not the other (THE regression this round
    # fixed). Arms recorded under different shell_mode values must never be pooled/compared.
    (("runtime", "shell_mode"), "shell_mode"),
)

def _valid_seed_base(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _effective_seed_base(manifest: dict):
    """C125: (base, problem). Only an ABSENT `runtime.seed_base` means a pre-flag manifest: those
    rows were all generated with `sample_seed(id, 0)`, which IS base 0. A PRESENT value must be a
    non-negative int (bool excluded); anything else (null, "0", -1, True) is a problem, never 0."""
    runtime = manifest.get("runtime") if isinstance(manifest, dict) else None
    if not isinstance(runtime, dict) or "seed_base" not in runtime:
        return 0, None
    v = runtime["seed_base"]
    if _valid_seed_base(v):
        return v, None
    return None, f"runtime.seed_base={v!r} is not a non-negative int"


_LLM_TIMEOUT_FIELD = ("runtime", "llm_timeout_s")


def _dig(d: dict, path: tuple):
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def read_manifest(path) -> dict | None:
    """None on ANY read/parse failure (missing file, invalid UTF-8, invalid JSON) -- an
    unreadable manifest is unknown provenance, never silently treated as an empty/matching one
    (that would let the comparability gate pass on NO evidence)."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def load_arm(model: str, rows_path, manifest_path=None) -> dict:
    """{"model", "rows_path", "manifest_path", "rows": [...], "manifest": {...}|None}.
    `manifest_path` defaults to the rows file's sibling `<stem>.manifest.json`
    (`run_agentbench_os.manifest_path_for`), the SAME convention run_agentbench_os itself uses."""
    rows_path = Path(rows_path)
    manifest_path = Path(manifest_path) if manifest_path else R.manifest_path_for(rows_path)
    return {"model": model, "rows_path": rows_path, "manifest_path": manifest_path,
           "rows": R.read_rows(rows_path), "manifest": read_manifest(manifest_path)}


def check_comparability(arms: list) -> list:
    """Every OTHER arm's manifest checked against the FIRST arm's, field by field
    (`_GATE_FIELDS`). Returns a list of human-readable mismatch messages; empty means
    comparable. A missing manifest on any arm is reported on its own (nothing else can be
    checked without it)."""
    missing = [a["model"] for a in arms if a["manifest"] is None]
    if missing:
        return [f"missing/unreadable manifest for: {', '.join(missing)}"]
    problems = []
    base = arms[0]
    for key_path, label in _GATE_FIELDS:
        base_val = _dig(base["manifest"], key_path)
        for other in arms[1:]:
            val = _dig(other["manifest"], key_path)
            if val != base_val:
                problems.append(f"{label} differs: {base['model']}={base_val!r} vs "
                                f"{other['model']}={val!r}")
    # C125: seed_base. Manifest level (absent counts as 0; invalid refuses), then ROW level.
    bases = {}
    for arm in arms:
        sb, bad = _effective_seed_base(arm["manifest"])
        if bad:
            problems.append(f"seed_base invalid for {arm['model']}: {bad}")
        bases[arm["model"]] = sb
    first = bases[base["model"]]
    for other in arms[1:]:
        sb = bases[other["model"]]
        if sb is not None and first is not None and sb != first:
            problems.append(f"seed_base differs: {base['model']}={first!r} vs "
                            f"{other['model']}={sb!r} (a missing runtime.seed_base counts as 0)")
    for arm in arms:
        sb = bases[arm["model"]]
        if sb is None:
            continue
        for r in arm["rows"]:
            rb = r.get("seed_base", 0)
            if rb != sb or isinstance(rb, bool):
                problems.append(f"seed_base row/manifest mismatch for {arm['model']}: item "
                                f"{r.get('id')!r} row seed_base={rb!r} vs manifest {sb!r}")
                break
            if "sampler_seed" in r:
                want = rowschema.sample_seed(r.get("id"), 0, base=sb)
                if r["sampler_seed"] != want:
                    problems.append(f"sampler_seed mismatch for {arm['model']}: item {r.get('id')!r} "
                                    f"row sampler_seed={r['sampler_seed']!r} vs expected {want!r} "
                                    f"for seed_base {sb!r}")
                    break
    return problems


def llm_timeout_note(arms: list) -> str | None:
    """llm_timeout_s differences are ALLOWED (it is a derived number, see module docstring) but
    always printed -- returns a human-readable note, or None when every arm agrees."""
    vals = {a["model"]: _dig(a["manifest"], _LLM_TIMEOUT_FIELD) for a in arms}
    if len(set(vals.values())) > 1:
        return "llm_timeout_s differs (allowed, derived): " + ", ".join(
            f"{m}={v}" for m, v in vals.items())
    return None


# --------------------------------------------------------------------------- per-arm statistics
def _percentile(sorted_vals: list, q: float):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    import math
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def _per_group_pass_rate(graded_rows: list) -> dict:
    """DIAGNOSTIC ONLY (AGENTS.md) -- never a ranking input, always labelled as such wherever
    this is printed. Same denominator convention as acc: setup_error rows are excluded (the
    caller passes GRADED rows only)."""
    buckets: dict = {}
    for r in graded_rows:
        g = r.get("group")
        b = buckets.setdefault(g, [0, 0])
        b[1] += 1
        if r.get("passed") is True:
            b[0] += 1
    return {g: round(p / n, 3) if n else None for g, (p, n) in buckets.items()}


def per_arm_stats(model: str, rows: list, manifest: dict | None) -> dict:
    """Reuses `run_agentbench_os.summarize` for the core n/graded_n/acc/acc_strict/conv_rate/
    outcome_counts/exec_timeout_count/shell_died_count machinery (the canonical, already-tested
    definitions this project uses for a single arm) and adds what a cross-arm report additionally
    needs: the acc_strict budget NAME, the harness_error flag count, token/wall PERCENTILES
    (summarize only has mean/max), the per-group diagnostic, and the runaway tax."""
    base = R.summarize(rows)
    thinking_budget = ((manifest or {}).get("sampling") or {}).get("thinking_budget")
    graded_rows = [r for r in rows if not r.get("setup_error")]
    toks = sorted(r["completion_tokens_total"] for r in rows
                 if isinstance(r.get("completion_tokens_total"), (int, float)))
    walls = sorted(
        w for w in (
            r.get("wall_total_s") if isinstance(r.get("wall_total_s"), (int, float))
            else r.get("wall_s") for r in rows)
        if isinstance(w, (int, float)))
    harness_error_count = sum(1 for r in rows if r.get("harness_error"))
    outcome_counts = {
        "solved": base["outcome_counts"].get("solved", 0),
        "failed_tests": base["outcome_counts"].get("failed_tests", 0),
        "turn_cap": base["outcome_counts"].get("turn_cap", 0),
        "exec_timeout": base["exec_timeout_count"],
        "shell_died": base["shell_died_count"],
        "setup_error": base["setup_error_count"],
        "harness_error": harness_error_count,
    }
    # runaway tax: turn_cap + exec_timeout, UNION (a row can carry exec_timeout without the
    # outcome itself being turn_cap) -- never double-counted.
    runaway_rows = [r for r in rows if r.get("outcome") == "turn_cap" or r.get("exec_timeout")]
    runaway_wall = sum(
        (r.get("wall_total_s") if isinstance(r.get("wall_total_s"), (int, float))
         else r.get("wall_s")) or 0.0
        for r in runaway_rows)
    total_wall = sum(walls)
    return {
        "model": model, "n": base["n"], "graded_n": base["graded_n"],
        "graded_ids": base["graded_ids"],
        "acc": base["acc"],                              # capability ceiling
        "acc_strict": base["acc_strict"], "acc_strict_budget": thinking_budget,
        "conv_rate": base["conv_rate"], "nonconv_kind_counts": base["nonconv_kind_counts"],
        "outcome_counts": outcome_counts,
        "tokens": {"mean": base["completion_tokens_mean"],
                  "median": round(statistics.median(toks), 1) if toks else None,
                  "p90": round(_percentile(toks, 0.90), 1) if toks else None,
                  "max": base["completion_tokens_max"]},
        "wall_total_s": {"mean": base["wall_total_s_mean"],
                         "p90": round(_percentile(walls, 0.90), 1) if walls else None,
                         "max": base["wall_total_s_max"]},
        "per_group_pass_rate_diagnostic": _per_group_pass_rate(graded_rows),
        "runaway_tax": {
            "n": len(runaway_rows),
            "share": round(len(runaway_rows) / base["n"], 3) if base["n"] else None,
            "wall_share": round(runaway_wall / total_wall, 3) if total_wall else None,
        },
    }


# --------------------------------------------------------------------------- pairwise statistics
def _acc_strict_per_item(rows: list) -> dict:
    """{id: [1.0 or 0.0]} -- acc_strict's own definition (passed AND converged), k=1 (ONE draw
    per item, as every AgentBench-OS row is -- the coordinator's own framing: "items are the
    clusters; k=1"). setup_error rows are excluded (not GRADED), same denominator as acc/
    acc_strict everywhere else in this report."""
    out = {}
    for r in rows:
        if r.get("setup_error"):
            continue
        rid = r.get("id")
        if rid is None:
            continue
        out[rid] = [1.0 if (r.get("passed") is True and r.get("converged") is True) else 0.0]
    return out


def pairwise_stats(model_a: str, rows_a: list, model_b: str, rows_b: list, *,
                   iters: int = 10000, seed: int = 0, margin: float = 0.05,
                   alpha: float = 0.05, power: float = 0.80, p_d: float = 0.20) -> dict:
    """Every pairwise figure the report prints, on the INTERSECTION of GRADED ids. Returns
    `{"comparable": False, "reason", "intersection_n": 0, ...}` when there is no shared item at
    all; otherwise `{"comparable": True, "intersection_n", "dropped_a_only", "dropped_b_only",
    "acc_strict_a", "acc_strict_b", "delta" (stats.paired_delta's full dict: delta/lo/hi/verdict/
    n_items/mde), "mcnemar_b", "mcnemar_c", "mcnemar_p", "exclusive_a", "exclusive_b", "mde"}`."""
    pa_full = _acc_strict_per_item(rows_a)
    pb_full = _acc_strict_per_item(rows_b)
    ids_a, ids_b = set(pa_full), set(pb_full)
    shared = sorted(ids_a & ids_b)
    dropped_a = sorted(ids_a - ids_b)
    dropped_b = sorted(ids_b - ids_a)
    result = {"model_a": model_a, "model_b": model_b, "intersection_n": len(shared),
             "dropped_a_only": dropped_a, "dropped_b_only": dropped_b}
    if not shared:
        result["comparable"] = False
        result["reason"] = "no shared GRADED items between the two arms"
        return result
    pa = {i: pa_full[i] for i in shared}
    pb = {i: pb_full[i] for i in shared}
    delta = stats.paired_delta(pa, pb, iters=iters, seed=seed, margin=margin)
    b = sum(1 for i in shared if pa[i][0] == 1.0 and pb[i][0] == 0.0)
    c = sum(1 for i in shared if pa[i][0] == 0.0 and pb[i][0] == 1.0)
    result.update({
        "comparable": True,
        "acc_strict_a": stats.pass_at_1(pa), "acc_strict_b": stats.pass_at_1(pb),
        "delta": delta,
        "mcnemar_b": b, "mcnemar_c": c, "mcnemar_p": stats.mcnemar_exact(b, c),
        "exclusive_a": sorted(i for i in shared if pa[i][0] == 1.0 and pb[i][0] == 0.0),
        "exclusive_b": sorted(i for i in shared if pb[i][0] == 1.0 and pa[i][0] == 0.0),
        "mde": stats.mde(len(shared), p_d=p_d, alpha=alpha, power=power),
    })
    return result


# --------------------------------------------------------------------------- the full report
def build_report(arms: list, *, iters: int = 10000, seed: int = 0, margin: float = 0.05,
                 alpha: float = 0.05, power: float = 0.80, p_d: float = 0.20) -> dict:
    """The comparability gate runs FIRST and unconditionally -- no statistic is computed at all
    when it refuses. Otherwise: per-arm stats for every arm, pairwise stats for EVERY pair, and a
    Holm correction applied across the whole pairwise family's McNemar p-values (the family is
    every comparable pair in THIS report run, declared up front)."""
    problems = check_comparability(arms)
    if problems:
        return {"comparable": False, "problems": problems}
    per_arm = [per_arm_stats(a["model"], a["rows"], a["manifest"]) for a in arms]
    pairs = []
    for i in range(len(arms)):
        for j in range(i + 1, len(arms)):
            pairs.append(pairwise_stats(
                arms[i]["model"], arms[i]["rows"], arms[j]["model"], arms[j]["rows"],
                iters=iters, seed=seed, margin=margin, alpha=alpha, power=power, p_d=p_d))
    comparable_pairs = [p for p in pairs if p.get("comparable")]
    adjusted = stats.holm([p["mcnemar_p"] for p in comparable_pairs]) if comparable_pairs else []
    for p, a in zip(comparable_pairs, adjusted):
        p["mcnemar_p_holm"] = a
    return {"comparable": True, "llm_timeout_note": llm_timeout_note(arms), "arms": per_arm,
           "pairs": pairs,
           "params": {"iters": iters, "seed": seed, "margin": margin, "alpha": alpha,
                     "power": power, "p_d": p_d}}


# --------------------------------------------------------------------------- markdown rendering
def _fmt(x, nd=3):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def render_markdown(report: dict, *, cli_line: str | None = None) -> str:
    if not report.get("comparable"):
        lines = ["# M54 AgentBench OS -- cross-arm comparison: REFUSED", ""]
        if cli_line:
            lines += [f"`{cli_line}`", ""]
        lines.append("Arms are not comparable -- the comparability gate refused before "
                     "computing any statistic:")
        for p in report["problems"]:
            lines.append(f"- {p}")
        return "\n".join(lines) + "\n"

    arms = report["arms"]
    pairs = report["pairs"]
    params = report["params"]
    lines = ["# M54 AgentBench OS -- cross-arm comparison", ""]
    if cli_line:
        lines += [f"`{cli_line}`", ""]
    if report.get("llm_timeout_note"):
        lines += [f"NOTE: {report['llm_timeout_note']}", ""]
    lines += [f"Bootstrap: iters={params['iters']} seed={params['seed']} "
             f"TOST margin={params['margin']} (+-{params['margin'] * 100:.0f}pp); "
             f"MDE alpha={params['alpha']} power={params['power']} p_d={params['p_d']}", ""]

    # ---- the four numbers the project reports, per arm.
    lines += ["## The four numbers (per arm)", "",
             "capability ceiling = acc (raw `passed`, NOT gated by convergence); "
             "edit/agent competence = acc_strict (passed AND converged -- the ranking metric, "
             "at the named thinking budget); latency per task = wall_total_s; "
             "runaway tax = turn_cap + exec_timeout share of n and their share of total "
             "wall-clock. NEVER RANK ON TOKENS OR WALL-CLOCK -- reported as plain distributions, "
             "never a composite.", "",
             "| model | n | graded_n | capability ceiling (acc) | acc_strict@budget | "
             "wall_total_s mean/p90/max | runaway tax n (share) / wall share |",
             "|---|---|---|---|---|---|---|"]
    for a in arms:
        lines.append(
            f"| {a['model']} | {a['n']} | {a['graded_n']} | {_fmt(a['acc'])} | "
            f"{_fmt(a['acc_strict'])}@{a['acc_strict_budget']} | "
            f"{_fmt(a['wall_total_s']['mean'], 1)}/{_fmt(a['wall_total_s']['p90'], 1)}/"
            f"{_fmt(a['wall_total_s']['max'], 1)} | "
            f"{a['runaway_tax']['n']} ({_fmt(a['runaway_tax']['share'])}) / "
            f"{_fmt(a['runaway_tax']['wall_share'])} |")
    lines.append("")

    # ---- full per-arm detail.
    lines += ["## Per-arm detail", ""]
    for a in arms:
        lines += [f"### {a['model']}", "",
                 f"- n={a['n']} graded_n={a['graded_n']}",
                 f"- acc (capability ceiling) = {_fmt(a['acc'])}",
                 f"- acc_strict@{a['acc_strict_budget']} (edit/agent competence, ranking metric) "
                 f"= {_fmt(a['acc_strict'])}",
                 f"- conv_rate = {_fmt(a['conv_rate'])}; "
                 f"nonconv_kinds = {a['nonconv_kind_counts']}",
                 f"- outcome counts: {a['outcome_counts']}",
                 f"- tokens per task: mean={_fmt(a['tokens']['mean'], 1)} "
                 f"median={_fmt(a['tokens']['median'], 1)} p90={_fmt(a['tokens']['p90'], 1)} "
                 f"max={_fmt(a['tokens']['max'], 1)}",
                 f"- wall_total_s per task: mean={_fmt(a['wall_total_s']['mean'], 1)} "
                 f"p90={_fmt(a['wall_total_s']['p90'], 1)} max={_fmt(a['wall_total_s']['max'], 1)}",
                 f"- per-group pass rate (DIAGNOSTIC ONLY, never a ranking input): "
                 f"{a['per_group_pass_rate_diagnostic']}",
                 f"- runaway tax (turn_cap + exec_timeout): n={a['runaway_tax']['n']} "
                 f"share={_fmt(a['runaway_tax']['share'])} "
                 f"wall_share={_fmt(a['runaway_tax']['wall_share'])}",
                 ""]

    # ---- pairwise.
    lines += ["## Pairwise comparisons (acc_strict, on the intersection of graded ids)", ""]
    for p in pairs:
        lines.append(f"### {p['model_a']} vs {p['model_b']}")
        lines.append("")
        lines.append(f"- intersection n = {p['intersection_n']} "
                     f"(dropped {len(p['dropped_a_only'])} {p['model_a']}-only, "
                     f"{len(p['dropped_b_only'])} {p['model_b']}-only"
                     + (f"; {p['model_a']}-only ids: {p['dropped_a_only'][:10]}"
                        if p["dropped_a_only"] else "")
                     + (f"; {p['model_b']}-only ids: {p['dropped_b_only'][:10]}"
                        if p["dropped_b_only"] else "") + ")")
        if not p.get("comparable"):
            lines.append(f"- NOT COMPARABLE: {p['reason']}")
            lines.append("")
            continue
        d = p["delta"]
        lines += [
            f"- acc_strict: {p['model_a']}={_fmt(p['acc_strict_a'])} "
            f"{p['model_b']}={_fmt(p['acc_strict_b'])}",
            f"- paired delta = {_fmt(d['delta'])} 95% CI [{_fmt(d['lo'])}, {_fmt(d['hi'])}] "
            f"-- TOST verdict (+-{report['params']['margin'] * 100:.0f}pp): **{d['verdict']}**",
            f"- exact McNemar: b={p['mcnemar_b']} (exclusive to {p['model_a']}) "
            f"c={p['mcnemar_c']} (exclusive to {p['model_b']}) "
            f"p={_fmt(p['mcnemar_p'], 4)} (Holm-adjusted: {_fmt(p.get('mcnemar_p_holm'), 4)})",
            f"- exclusive-solve sets: {p['model_a']} only solves "
            f"{len(p['exclusive_a'])} ({p['exclusive_a'][:10]}); {p['model_b']} only solves "
            f"{len(p['exclusive_b'])} ({p['exclusive_b'][:10]})",
            f"- nominal MDE at n={p['intersection_n']} (p_d={report['params']['p_d']}) "
            f"= {_fmt(p['mde'])}",
            ""]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- CLI
def _parse_kv(s: str, flag: str) -> tuple:
    if "=" not in s:
        raise argparse.ArgumentTypeError(f"{flag} needs MODEL=PATH, got {s!r}")
    model, path = s.split("=", 1)
    return model, path


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", action="append", required=True, metavar="MODEL=PATH",
                    help="repeatable; full registry model name=path to its rows.jsonl")
    ap.add_argument("--manifest", action="append", default=[], metavar="MODEL=PATH",
                    help="optional override; default is the rows file's sibling "
                         "<stem>.manifest.json")
    ap.add_argument("--out", required=True,
                    help="markdown report path; a JSON sidecar is also written "
                         "(<out stem>.json)")
    ap.add_argument("--iters", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--margin", type=float, default=0.05, help="TOST equivalence margin")
    ap.add_argument("--alpha", type=float, default=0.05)
    ap.add_argument("--power", type=float, default=0.80)
    ap.add_argument("--p-d", dest="p_d", type=float, default=0.20,
                    help="guessed discordant-pair rate, for the nominal MDE")
    return ap


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    args = build_arg_parser().parse_args(argv)
    try:
        rows_kv = [_parse_kv(s, "--rows") for s in args.rows]
        manifest_kv = dict(_parse_kv(s, "--manifest") for s in args.manifest)
    except argparse.ArgumentTypeError as e:
        # _parse_kv is called OUTSIDE argparse's own parsing step (it needs the already-parsed
        # --rows/--manifest LISTS), so argparse never gets a chance to turn this into its own
        # clean usage error -- catch it here instead of letting it crash as an uncaught exception.
        print(f"[agentbench_compare] REFUSED: {e}", file=sys.stderr, flush=True)
        return 2
    models = [m for m, _ in rows_kv]
    if len(models) != len(set(models)):
        print(f"[agentbench_compare] REFUSED: duplicate --rows model name(s) in {models}",
             file=sys.stderr, flush=True)
        return 2
    if len(rows_kv) < 2:
        print("[agentbench_compare] REFUSED: need at least 2 --rows arms to compare",
             file=sys.stderr, flush=True)
        return 2
    arms = [load_arm(model, rows_path, manifest_kv.get(model)) for model, rows_path in rows_kv]
    empty = [a["model"] for a in arms if not a["rows"]]
    if empty:
        print(f"[agentbench_compare] REFUSED: no rows for: {', '.join(empty)}",
             file=sys.stderr, flush=True)
        return 2
    report = build_report(arms, iters=args.iters, seed=args.seed, margin=args.margin,
                          alpha=args.alpha, power=args.power, p_d=args.p_d)
    if not report["comparable"]:
        print("[agentbench_compare] REFUSED: arms are not comparable:", file=sys.stderr,
             flush=True)
        for p in report["problems"]:
            print(f"  - {p}", file=sys.stderr, flush=True)
        return 2
    cli_line = "python -m bench.agentbench_compare " + " ".join(argv)
    md = render_markdown(report, cli_line=cli_line)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[agentbench_compare] wrote {out_path}")
    print(f"[agentbench_compare] wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

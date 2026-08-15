"""Bridge aider polyglot results INTO the results corpus, so the agentic axis is in the scoresheet.

WHY THIS EXISTS. The n=110 aider result is the campaign's only powered capability finding
(`final` 73.6% vs 50.0%, McNemar p=1.3e-05) and the entire basis of the coding pick — and it was
ABSENT from the scoresheet, because aider writes a `.aider.results.json` per exercise inside its own
benchmark checkout rather than into `benchmark/results/`. `scoreboard.py` globs `results/*/*.jsonl`,
so the axis showed as `missing aider` for every model while the number lived in a doc.

DESIGN: write into the corpus rather than teach the scoreboard to read aider's tree. The checkout is
a working directory that gets re-run and deleted; rows in the corpus are archived, fingerprinted and
git-tracked like every other row. Costs one denormalised copy. `scoreboard.py` needs NO change.

THREE SCHEMA DECISIONS, each avoiding a known false number:

1. `completion_tokens_sum`, NOT `completion_tokens`. aider records completion_tokens as a per-case
   SUM ACROSS TURNS. Writing that into the canonical field would feed a sum to a PER-TURN budget
   comparison — which already produced a wrong claim once ("max completion 62,083 against an 81,920
   budget"; the real per-turn max was 148,908).
2. `converged` is left None, and the scoresheet renders `n/a`. Convergence is a per-turn property
   and aider gives us no per-turn view, so emitting True would fabricate a 100% conv column.
3. The manifest records M1's REAL config: `max_kv_cache_size` 65536, so the resolved thinking budget
   was ~52,390 rather than the declared 81,920. Stamping 81,920 would make `compare` treat these
   rows as budget-matched with the evalplus rows (which ran at 131072 and genuinely got 81,920) —
   exactly the false-match the provenance fingerprint work eliminated.

`acc` = fraction of cases whose LAST attempt passed (aider's own credit rule, what `final` means).
`acc_strict` additionally zeroes cases that exhausted their context window — the aider analogue of a
truncated draw, and non-zero in practice (2 Ornith, 1 distill on m1f).
"""
from __future__ import annotations

import json
import os

from . import aider_adapter

BENCH = "aider"
SCHEMA_VERSION = 1

# m1f is the n=110 matched run. A later partial `m1g-distill-java` exists in the same benchmark dir;
# pooling it would be the apples-to-apples violation collect_case_results' run_name guard prevents.
M1F_LANGS = ("python", "javascript", "go", "rust", "java")


#: RECOVERY overlays: (tag, lang) runs that RE-RAN cases a prior run failed to EXECUTE.
#:
#: This is NOT pooling two complete runs of one model — that is the apples-to-apples violation
#: `collect_case_results`' run_name guard exists to prevent, and it stays prevented. A recovery is
#: the narrow case where infrastructure, not the model, stopped cases from running at all.
#:
#: MEASURED: `m1f-distill-java` lost 21 of 22 cases to a TCC failure — the files exist but carry no
#: `tests_outcomes`, i.e. aider set the exercise up and never ran it. `m1g-distill-java` re-ran all
#: 22 cleanly (46 requests, zero 500s). Commit a182a47 pooled them to reach the published n=110;
#: without the overlay this bridge reproduces the SUPERSEDED interim figure (66/89 = 74.2%) instead
#: of the published 81/110 = 73.6%, which is exactly what it did on first run.
M1_RECOVERY = {"distill": (("m1g", "java"),)}


def _ran(case: dict) -> bool:
    """aider writes a results file for every exercise it SETS UP; only a non-empty
    `tests_outcomes` means it actually ran. Counting set-up-but-never-run cases as failures would
    silently move the denominator (the distill would read 60.0% instead of 73.6%)."""
    return bool(case.get("tests_outcomes")) and bool(case.get("testcase"))


def collect_arm_cases(bench_dir, arm: str, langs=M1F_LANGS, tag: str = "m1f",
                      recovery=None) -> dict:
    """{'<lang>/<exercise>': case} for one arm, keyed so arms pair item-by-item.

    `recovery` defaults to M1_RECOVERY[arm]; pass () to disable. Overlay cases WIN over base ones,
    because the overlay is the run that actually executed.
    """
    if recovery is None:
        recovery = M1_RECOVERY.get(arm, ())
    cases = {}
    for lang in langs:
        for c in aider_adapter.collect_case_results(bench_dir, run_name=f"{tag}-{arm}-{lang}"):
            if _ran(c):
                cases[f"{lang}/{c['testcase']}"] = c
    for rtag, rlang in recovery:
        for c in aider_adapter.collect_case_results(bench_dir, run_name=f"{rtag}-{arm}-{rlang}"):
            if _ran(c):
                cases[f"{rlang}/{c['testcase']}"] = c      # overlay wins
    return cases


def _row(item_id: str, model: str, case: dict) -> dict:
    return {
        "id": item_id,
        "model": model,
        "bench": BENCH,
        "sample": 0,
        "schema_version": SCHEMA_VERSION,
        "passed": bool(case.get("passed")),
        "wall_s": case.get("duration"),
        # PER-CASE SUMS across turns — deliberately not `completion_tokens`/`prompt_tokens`.
        "completion_tokens_sum": case.get("completion_tokens"),
        "prompt_tokens_sum": case.get("prompt_tokens"),
        "edit_format": case.get("edit_format"),
        "n_malformed": case.get("num_malformed_responses"),
        # NOTE the NORMALISED key: aider_adapter aliases the raw `num_exhausted_context_windows`
        # to `exhausted_context_windows`. Reading the raw name silently yields None, which made
        # acc_strict equal acc and hid every context-exhausted case.
        "n_context_exhausted": case.get("exhausted_context_windows"),
        "test_timeouts": case.get("test_timeouts"),
        "tests_outcomes": case.get("tests_outcomes"),
        # Convergence is per-TURN; aider gives no per-turn view. None => scoresheet shows n/a.
        "converged": None,
    }


def build(bench_dir, arm: str, model: str, langs=M1F_LANGS, tag: str = "m1f",
          recovery=None) -> tuple[list, dict]:
    """Return (rows, score) for one arm. `score` matches what grade_all writes per pair."""
    cases = collect_arm_cases(bench_dir, arm, langs, tag, recovery)
    rows = [_row(k, model, cases[k]) for k in sorted(cases)]
    n = len(rows)
    passed = sum(1 for r in rows if r["passed"])
    strict = sum(1 for r in rows if r["passed"] and not (r["n_context_exhausted"] or 0))
    score = {
        "benchmark": BENCH, "model": model, "n": n,
        "acc": (passed / n) if n else None,
        "acc_strict": (strict / n) if n else None,
        "items": [{"id": r["id"], "sample": 0, "score": 1.0 if r["passed"] else 0.0} for r in rows],
        "n_context_exhausted": sum(1 for r in rows if (r["n_context_exhausted"] or 0)),
        "n_malformed": sum((r["n_malformed"] or 0) for r in rows),
        "note": ("acc = last-attempt pass (aider's `final`); acc_strict additionally zeroes "
                 "context-exhausted cases. converged is null: per-turn data is unavailable."),
    }
    return rows, score


def write_arm(results_root, arm: str, model: str, bench_dir, manifest: dict | None = None,
              langs=M1F_LANGS, tag: str = "m1f", recovery=None) -> dict:
    """Write results/<model>/aider.{jsonl,score.json,manifest.json}. Returns the score."""
    rows, score = build(bench_dir, arm, model, langs, tag, recovery)
    out = os.path.join(os.fspath(results_root), model)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, f"{BENCH}.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    with open(os.path.join(out, f"{BENCH}.score.json"), "w") as fh:
        json.dump(score, fh, indent=1, sort_keys=True)
    if manifest is not None:
        with open(os.path.join(out, f"{BENCH}.manifest.json"), "w") as fh:
            json.dump(manifest, fh, indent=1, sort_keys=True)
    return score

"""Adapter that drives the official Aider polyglot benchmark against our mlx-serve
OpenAI-compatible endpoint and normalizes its pass-rate. Aider's harness does its own
edit loop + per-exercise test execution; we only orchestrate + parse. The harness +
exercises install/clone only where this runs (optional); detected lazily, graceful-degrade.

WHY THIS MODULE READS AIDER'S JSON AND NOT JUST ITS STDOUT
----------------------------------------------------------
Scraping `pass_rate_N` off stdout throws away every operational-reliability signal aider already
measured, and the campaign paid for that three times:

* 2026-07-06, `gemma-4-26B-A4B-it-OptiQ-4bit` was filed as "20% pass_rate_2" and was in fact
  CONTAMINATED — 5/5 cases hit the OUTPUT-token cap after long thinking (`Input ~2,283 of 98,304`
  was fine; `Output ~0 of 32,768` was not). Aider counts that as `num_exhausted_context_windows`,
  a MISLABEL that reads as an input-context problem. `output_limit_hits` + `OUTPUT_LIMIT_NOTE`
  exist so the number arrives with its own correction attached.
* the same session's "well-formed 94.1%" for `Ornith-1.0-35B-mlx-uniform-4bit` was read BY HAND
  out of aider's console output; nothing parsed it, so nothing could regress-check it.
* a run "stalled at case 17 on a router-timeout retry loop" — diagnosable from per-case `duration`
  and `num_error_outputs`, which stdout does not carry per case.

SCHEMA PROVENANCE (verified, not guessed): every field name and the pass-rate arithmetic below are
transcribed from `benchmark/benchmark.py` in Aider-AI/aider at tag `v0.86.2` (the version installed
on this box) and cross-checked against `main` — the per-case `results = dict(...)` block and
`summarize_results()` are byte-identical between the two. Per case aider writes
`<run_dir>/<lang>/exercises/practice/<exercise>/.aider.results.json`; the run dir is
`<AIDER_BENCHMARK_DIR>/<YYYY-MM-DD-HH-MM-SS>--<run_name>`.
"""
import json
import os
import re
import subprocess
import sys

AXIS = "agentic_coding"

#: Aider's `num_exhausted_context_windows` fires on a length-finish (`FinishReasonLength`), i.e.
#: the OUTPUT budget ran out — `base_coder.py` increments it right after appending
#: "you sent too many tokens", which is the wrong diagnosis for a thinking model. Carrying this
#: string in every result dict is deliberate: the 2026-07-06 gemma-MoE run was nearly filed as an
#: input-context failure, and the fix (raise `max_tokens`, not the context) is the opposite one.
OUTPUT_LIMIT_NOTE = (
    "output_limit_hits mirrors aider's num_exhausted_context_windows, which is a MISLABEL: it "
    "counts OUTPUT-token-budget exhaustion (a length finish after long thinking), NOT input-context "
    "overflow. Diagnose it by raising max_tokens / shortening reasoning, never by shrinking the "
    "input context."
)

# Per-case keys, aider's spelling -> ours. Aggregate files spell some of them differently
# (`summarize_results` sums into `error_outputs` / `user_asks` / `exhausted_context_windows` and
# prints `total_cost`), so each entry lists every accepted spelling, most-specific first.
_INT_FIELDS = {
    "num_malformed_responses": ("num_malformed_responses",),
    "num_with_malformed_responses": ("num_with_malformed_responses",),
    "lazy_comments": ("lazy_comments",),
    "syntax_errors": ("syntax_errors",),
    "indentation_errors": ("indentation_errors",),
    "test_timeouts": ("test_timeouts",),
    "exhausted_context_windows": ("num_exhausted_context_windows", "exhausted_context_windows"),
    "num_error_outputs": ("num_error_outputs", "error_outputs"),
    "num_user_asks": ("num_user_asks", "user_asks"),
    "prompt_tokens": ("prompt_tokens",),
    "completion_tokens": ("completion_tokens",),
    "thinking_tokens": ("thinking_tokens",),
}
_FLOAT_FIELDS = {
    "duration": ("duration",),
    "cost": ("cost", "total_cost"),
    "pass_rate_1": ("pass_rate_1",),
    "pass_rate_2": ("pass_rate_2",),
}
_STR_FIELDS = {
    "testcase": ("testcase",),
    "model": ("model",),
    "edit_format": ("edit_format",),
    "commit_hash": ("commit_hash",),
    "reasoning_effort": ("reasoning_effort",),
}
#: Summed by aggregate_cases. `num_with_malformed_responses` is a CASE count, not a response count.
_SUMMED = ("num_malformed_responses", "num_with_malformed_responses", "lazy_comments",
           "syntax_errors", "indentation_errors", "test_timeouts", "exhausted_context_windows",
           "num_error_outputs", "num_user_asks", "prompt_tokens", "completion_tokens")


def aider_available(aider_repo: str) -> bool:
    """The aider benchmark harness lives in the aider REPO (not the pip package)."""
    return bool(aider_repo) and os.path.isfile(os.path.join(aider_repo, "benchmark", "benchmark.py"))


def parse_pass_rate(stdout: str) -> dict:
    """Extract pass_rate_1 / pass_rate_2 (percentages) from aider benchmark stdout.

    FALLBACK ONLY — `parse_aider_results` + `aggregate_cases` are the primary path. This stays
    because stdout is the one artifact that survives a run whose results tree was cleaned,
    overwritten by a later `--new` run, or written inside a container whose mount is gone. It
    reports two numbers and cannot report reliability, so a run scored from here is not
    comparable on the malformed/output-limit/duration columns.
    """
    out = {}
    for k in ("pass_rate_1", "pass_rate_2"):
        m = re.search(rf"{k}\s*[:=]\s*([0-9.]+)", stdout or "")
        out[k] = float(m.group(1)) if m else None
    return out


#: The plan doc's name for the stdout parser. Same function, kept so both names resolve.
parse_aider_report = parse_pass_rate


def _empty_case(note=None):
    out = {"parsed": False, "note": note, "tests_outcomes": None, "n_attempts": None,
           "passed": None, "passed_on_attempt": None,
           "output_limit_hits": None, "output_limit_note": OUTPUT_LIMIT_NOTE}
    for name in list(_INT_FIELDS) + list(_FLOAT_FIELDS) + list(_STR_FIELDS):
        out[name] = None
    return out


def _pick(d, names, cast):
    """First present, non-None, castable value among `names`. Unknown keys are never consulted."""
    for n in names:
        if n in d and d[n] is not None:
            try:
                return cast(d[n])
            except (TypeError, ValueError):
                return None
    return None


def parse_aider_results(path_or_dict) -> dict:
    """Normalize ONE aider result (a per-exercise `.aider.results.json` path, or a loaded dict).

    Tolerant by construction, because these files are written by a long-running benchmark we do
    not control: unknown keys are ignored (aider adds fields between releases), absent keys become
    None (never 0 — "no malformed responses" and "aider did not record it" are different claims,
    and only one of them is a model result), and a missing or truncated file returns
    `parsed: False` plus a `note` instead of raising. A run killed mid-write leaves exactly the
    truncated file this handles; crashing there would lose the other 33 cases.

    `parsed` is True whenever the JSON loaded — INCLUDING aider's `{"exception": traceback}` shape
    (`benchmark.py:675`), which is a real case file that counts toward aider's `completed_tests`
    denominator while carrying no outcome. That case gets `tests_outcomes: None` and a note.

    Outcome fields follow aider's own arithmetic (`summarize_results`): a case passed iff its LAST
    attempt passed (`tests_outcomes[-1]`) — `[True, False]` is a FAILURE, not a pass — and
    `passed_on_attempt` is 1-based. `[]` (no attempt completed) is not a pass.

    `output_limit_hits` mirrors `exhausted_context_windows`; see OUTPUT_LIMIT_NOTE.
    """
    if isinstance(path_or_dict, dict):
        raw = path_or_dict
    else:
        p = os.fspath(path_or_dict)
        if not os.path.isfile(p):
            return _empty_case(f"aider results file not found: {p}")
        try:
            with open(p, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, UnicodeDecodeError) as e:
            return _empty_case(f"aider results unreadable ({type(e).__name__}): {p}")
        except json.JSONDecodeError as e:
            # A run killed mid-write, or a container that vanished between write and flush.
            return _empty_case(f"aider results JSON corrupt/truncated at line {e.lineno}: {p}")
        if not isinstance(raw, dict):
            return _empty_case(f"aider results is not a JSON object: {p}")

    out = _empty_case()
    out["parsed"] = True
    for name, keys in _STR_FIELDS.items():
        out[name] = _pick(raw, keys, str)
    for name, keys in _INT_FIELDS.items():
        out[name] = _pick(raw, keys, int)
    for name, keys in _FLOAT_FIELDS.items():
        # aider stores aggregate pass rates as FORMATTED STRINGS (f"{pass_rate:.1f}").
        out[name] = _pick(raw, keys, float)

    outcomes = raw.get("tests_outcomes")
    if isinstance(outcomes, list):
        out["tests_outcomes"] = [bool(o) for o in outcomes]
        out["n_attempts"] = len(out["tests_outcomes"])
        out["passed"] = bool(out["tests_outcomes"] and out["tests_outcomes"][-1])
        out["passed_on_attempt"] = out["n_attempts"] if out["passed"] else None

    if out["num_with_malformed_responses"] is None and out["num_malformed_responses"] is not None:
        # Per case aider records only the response count; the CASE count is what
        # percent_cases_well_formed is built from, so derive it here rather than in the sum.
        out["num_with_malformed_responses"] = 1 if out["num_malformed_responses"] else 0
    out["output_limit_hits"] = out["exhausted_context_windows"]

    if raw.get("exception"):
        out["note"] = ("aider recorded an exception for this case (no tests ran): "
                       + str(raw["exception"]).strip().splitlines()[-1][:160])
    return out


def collect_case_results(bench_dir, run_name=None) -> list:
    """Every parsed per-case result under an aider benchmark dir. Never raises; [] when absent.

    Globs exactly what aider's own `load_results` globs
    (`*/exercises/practice/*/.aider.results.json`), tried both relative to a RUN dir and one level
    up so either a run dir or `AIDER_BENCHMARK_DIR` can be handed in. `run_name` restricts to
    `<timestamp>--<run_name>` (aider's `resolve_dirname` prefixes a timestamp) — without it, two
    runs of the same model in one benchmark dir would silently POOL into one score, which is the
    apples-to-apples violation this whole harness exists to prevent. Results are path-sorted so
    aggregates are order-independent.
    """
    from pathlib import Path
    root = Path(os.fspath(bench_dir))
    leaf = "*/exercises/practice/*/.aider.results.json"
    if run_name:
        patterns = [f"*--{run_name}/{leaf}", f"{run_name}/{leaf}"]
    else:
        patterns = [leaf, f"*/{leaf}"]
    paths = []
    for pat in patterns:
        try:
            paths.extend(root.glob(pat))
        except OSError:
            continue
    return [parse_aider_results(str(p)) for p in sorted(set(paths))]


def aggregate_cases(cases) -> dict:
    """Aggregate per-case aider results into one reliability-bearing row. Never raises.

    `cases` may hold raw aider dicts, already-parsed dicts, or paths — each goes through
    `parse_aider_results`, so mixed input is fine.

    PASS-RATE SEMANTICS, copied from aider's `summarize_results` so our numbers are comparable to
    the public leaderboard: a case is credited iff its LAST attempt passed, and it is credited to
    `pass_rate_N` for every N >= len(tests_outcomes). Hence `[False, True]` counts for pass_rate_2
    only, `[True]` counts for both, `[]` and `[True, False]` count for neither. The DENOMINATOR is
    every case whose file parsed — including cases that crashed before running a test, exactly as
    aider's `completed_tests` does.

    That denominator is also a trap, so it is instrumented rather than hidden: `n_scored` counts
    cases that actually reached a test and `n_crashed` those that did not. When `n_scored == 0`
    the pass rates are None (a run where nothing ran is NOT a 0% model result — aider would print
    0.0 and the campaign would file it as capability); `n_unparsed` counts files aider itself would
    have skipped (`json.JSONDecodeError`).

    Durations are kept as a LIST, split by outcome (`durations_success` / `durations_fail`),
    because `stats.time_to_success` needs the two MEANS separately and these runs are heavily
    right-tailed — a summary mean would hide the loop-prone tail that is the defect being measured.
    Cases with no recorded duration are OMITTED from the lists, never zeroed. `avg_duration`
    divides by observed durations (aider's `seconds_per_case` divides by `completed_tests`, which
    dilutes the average with crashed 0-duration cases).

    `model` / `edit_format` are reported only when UNANIMOUS: a pooled diff+whole run is
    format-confounded and must not present one label.
    """
    parsed = [c if (isinstance(c, dict) and "parsed" in c) else parse_aider_results(c)
              for c in (cases or [])]
    ok = [c for c in parsed if c.get("parsed")]
    n = len(ok)
    agg = {"n_cases": n, "n_unparsed": len(parsed) - n,
           "n_scored": sum(1 for c in ok if c["tests_outcomes"] is not None),
           "n_crashed": sum(1 for c in ok if c["tests_outcomes"] is None),
           "tries": max((c["n_attempts"] or 0) for c in ok) if ok else 0,
           "pass_rate_1": None, "pass_rate_2": None, "pass_rate_final": None,
           "pass_num_1": None, "pass_num_2": None,
           "percent_cases_well_formed": None,
           "durations": [], "durations_success": [], "durations_fail": [],
           "total_duration": None, "avg_duration": None, "total_cost": None,
           "model": None, "edit_format": None, "models": [], "edit_formats": [],
           "output_limit_hits": 0, "output_limit_note": OUTPUT_LIMIT_NOTE, "note": None}
    for name in _SUMMED:
        agg[name] = 0
    if not ok:
        agg["note"] = ("no parsable aider case results — nothing to aggregate"
                       + (f" ({agg['n_unparsed']} unparsable file(s))" if agg["n_unparsed"] else ""))
        return agg

    # Credit horizon: at least 2, because the deployed config always allows a second attempt and a
    # run where every case passed first try must still report pass_rate_2.
    horizon = max(agg["tries"], 2)
    passed_tests = [0] * horizon
    for c in ok:
        outcomes = c["tests_outcomes"] or []
        if outcomes and outcomes[-1]:
            for i in range(len(outcomes) - 1, horizon):
                passed_tests[i] += 1
        for name in _SUMMED:
            agg[name] += c[name] or 0
        if c["duration"] is not None:
            agg["durations"].append(c["duration"])
            (agg["durations_success"] if c["passed"] else agg["durations_fail"]).append(
                c["duration"])
        for key, bucket in (("model", "models"), ("edit_format", "edit_formats")):
            if c[key] and c[key] not in agg[bucket]:
                agg[bucket].append(c[key])

    agg["output_limit_hits"] = agg["exhausted_context_windows"]
    if agg["n_scored"]:
        agg["pass_num_1"], agg["pass_num_2"] = passed_tests[0], passed_tests[1]
        agg["pass_rate_1"] = 100.0 * passed_tests[0] / n
        agg["pass_rate_2"] = 100.0 * passed_tests[1] / n
        agg["pass_rate_final"] = 100.0 * passed_tests[horizon - 1] / n
        agg["percent_cases_well_formed"] = 100.0 * (1 - agg["num_with_malformed_responses"] / n)
    else:
        agg["note"] = (f"{n} case(s) parsed but NONE reached a test (all crashed) — no pass rate; "
                       f"this is a harness/serving failure, not a 0% model result")
    if agg["durations"]:
        agg["total_duration"] = sum(agg["durations"])
        agg["avg_duration"] = agg["total_duration"] / len(agg["durations"])
    costs = [c["cost"] for c in ok if c["cost"] is not None]
    agg["total_cost"] = sum(costs) if costs else None
    for key, bucket in (("model", "models"), ("edit_format", "edit_formats")):
        agg[key] = agg[bucket][0] if len(agg[bucket]) == 1 else None
    if agg["n_crashed"] and agg["note"] is None:
        agg["note"] = (f"{agg['n_crashed']} of {n} case(s) crashed before running a test and sit "
                       f"in the pass-rate DENOMINATOR (aider semantics)")
    return agg


def reliability_summary(agg) -> dict:
    """Operational-reliability view of an `aggregate_cases` row, incl. expected time-to-success.

    `stats.time_to_success(t_success, t_fail, p)` turns a pass rate plus the two mean durations
    into `expected_s` (wall-clock to a first success under independent retries) and
    `successes_per_hour`. That is the number an operator actually feels: 61.8% at ~6 min/case and
    75% at ~15 min/case are not ranked by pass rate alone. `p` is the FINAL pass rate
    (`pass_rate_final`), not pass_rate_1, because an aider case duration already includes its
    retry attempts — pairing whole-case durations with a first-try-only rate would double-charge.

    Degrades instead of raising (stats raises on an empty success list): with no observed success
    `expected_s` is None and `successes_per_hour` 0.0. `thin_evidence` flags fewer than ~5
    successes or ~5 failures, the floor below which those two means are single-sample guesses
    (stats.time_to_success's own stated minimum) — report the components, not the ratio.

    NO CAMPAIGN NUMBERS ARE BAKED IN ANYWHERE HERE, deliberately: the Ornith-vs-distill
    "384s @ 61.8% (n=34) vs 870s @ 75% (n=16)" pair is cross-session, cross-n and unmatched-item,
    so pinning it as an expectation would cement an apples-to-apples violation into the harness.
    """
    from . import stats
    agg = agg or {}
    t_s = list(agg.get("durations_success") or [])
    t_f = list(agg.get("durations_fail") or [])
    pr = agg.get("pass_rate_final")
    p = pr / 100.0 if pr is not None else None
    out = {"p": p, "n_cases": agg.get("n_cases") or 0,
           "n_success": len(t_s), "n_fail": len(t_f),
           "mean_success_s": sum(t_s) / len(t_s) if t_s else None,
           "mean_fail_s": sum(t_f) / len(t_f) if t_f else None,
           "expected_s": None, "successes_per_hour": None,
           "percent_cases_well_formed": agg.get("percent_cases_well_formed"),
           "num_malformed_responses": agg.get("num_malformed_responses"),
           "num_with_malformed_responses": agg.get("num_with_malformed_responses"),
           "test_timeouts": agg.get("test_timeouts"),
           "num_error_outputs": agg.get("num_error_outputs"),
           "output_limit_hits": agg.get("output_limit_hits"),
           "output_limit_note": OUTPUT_LIMIT_NOTE,
           "thin_evidence": True, "note": None}
    out["thin_evidence"] = len(t_s) < 5 or (p is not None and p < 1.0 and len(t_f) < 5)
    if p is None:
        out["note"] = "no pass rate available — cannot compute time-to-success"
        return out
    if not t_s or p == 0.0:
        out["successes_per_hour"] = 0.0
        out["note"] = ("no observed success (or no success duration) — expected time-to-success is "
                       "unbounded; report the failure durations instead")
        return out
    tts = stats.time_to_success(t_s, t_f, p)
    out["expected_s"] = tts["expected_s"]
    out["successes_per_hour"] = tts["successes_per_hour"]
    if p < 1.0 and not t_f:
        out["note"] = ("p<1 with NO observed failure durations — retries are charged 0s, so "
                       "expected_s is an OPTIMISTIC bound (failing cases recorded no duration)")
    elif out["thin_evidence"]:
        out["note"] = (f"thin evidence: {len(t_s)} success / {len(t_f)} failure duration(s); "
                       f"time_to_success needs ~5 of each before its means mean anything")
    return out


def run_aider(model, exercises_dir, aider_repo, edit_format="whole", num_tests=None,
              endpoint="http://localhost:8000/v1", run_name="bake",
              runner=subprocess.run) -> dict:
    """Drive the aider polyglot benchmark against the local mlx-serve endpoint and normalize
    the pass-rate. `runner` is injectable for tests. Never raises; graceful-degrade.

    Scoring precedence is STRUCTURED-FIRST: if aider's per-case `.aider.results.json` files are
    present under AIDER_BENCHMARK_DIR for this `run_name`, the row is scored from them
    (`source: "results_json"`) and carries the reliability vector — `percent_cases_well_formed`,
    `output_limit_hits`, per-case durations, `reliability.successes_per_hour`. Stdout is the
    documented fallback (`source: "stdout"`) and yields pass rates only; `acc`, `skipped`, `note`,
    `pass_rate_1`, `pass_rate_2` are present either way, so existing readers are unaffected.
    """
    base = {"model": model, "axis": AXIS, "tool": "aider_polyglot", "edit_format": edit_format}
    if not aider_available(aider_repo):
        return {**base, "acc": None, "skipped": True,
                "note": f"aider harness not found under {aider_repo!r}; "
                        f"clone Aider-AI/aider + polyglot-benchmark (see README)"}
    # AIDER_DOCKER: aider's benchmark.py refuses to run (prints a warning + returns, no exercises)
    # unless this is set — a guard against running unvetted model code outside a container. We run
    # on the host (all polyglot toolchains present + a controlled benchmark), so set it explicitly.
    env = {**os.environ, "OPENAI_API_BASE": endpoint, "OPENAI_API_KEY": "sk-local",
           "AIDER_DOCKER": "1"}
    # The polyglot python exercises run `pytest` via subprocess; it lives in the aider venv
    # (== the python running benchmark.py). Prepend that bindir so the test-runner finds it
    # (other langs — cargo/go/npm/javac/g++ — resolve from the inherited PATH).
    env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
    # benchmark.py asserts BENCHMARK_DNAME (default relative "tmp.benchmarks") exists; we run from
    # an arbitrary CWD, so pin it to an absolute dir under the aider repo (and create it).
    bench_workdir = os.path.join(aider_repo, "benchmark", "tmp.benchmarks")
    try:
        os.makedirs(bench_workdir, exist_ok=True)
    except OSError:
        pass
    env["AIDER_BENCHMARK_DIR"] = bench_workdir
    cmd = [sys.executable, os.path.join(aider_repo, "benchmark", "benchmark.py"), run_name,
           "--model", f"openai/{model}", "--edit-format", edit_format,
           "--threads", "1", "--exercises-dir", exercises_dir, "--new"]
    if num_tests is not None:
        cmd += ["--num-tests", str(num_tests)]
    try:
        proc = runner(cmd, env=env, capture_output=True, text=True)
    except Exception as e:  # noqa: BLE001 — harness/python launch failure; degrade
        return {**base, "acc": None, "skipped": False,
                "note": f"aider runner raised: {type(e).__name__}: {str(e)[:120]}"}
    rc = getattr(proc, "returncode", 1)
    if rc != 0:
        return {**base, "acc": None, "skipped": False,
                "note": f"aider benchmark failed rc={rc}: {(getattr(proc, 'stderr', '') or '')[:160]}"}
    stdout = getattr(proc, "stdout", "") or ""
    agg = None
    cases = collect_case_results(bench_workdir, run_name=run_name)
    if cases:
        agg = aggregate_cases(cases)
    if agg is not None and agg.get("pass_rate_final") is not None:
        return {**base,
                "pass_rate_1": agg["pass_rate_1"], "pass_rate_2": agg["pass_rate_2"],
                "acc": agg["pass_rate_final"] / 100.0, "skipped": False,
                "source": "results_json", "note": agg["note"],
                "n_cases": agg["n_cases"],
                "percent_cases_well_formed": agg["percent_cases_well_formed"],
                "output_limit_hits": agg["output_limit_hits"],
                "output_limit_note": OUTPUT_LIMIT_NOTE,
                "aider_results": agg, "reliability": reliability_summary(agg),
                "stdout_pass_rate": parse_pass_rate(stdout)}
    if agg is not None:
        # Case files exist but nothing reached a test: NOT a 0% result (see aggregate_cases).
        return {**base, "pass_rate_1": None, "pass_rate_2": None, "acc": None, "skipped": False,
                "source": "results_json",
                "note": agg["note"] or "aider results present but carry no pass rate",
                "n_cases": agg["n_cases"], "aider_results": agg, "reliability": None,
                "stdout_pass_rate": parse_pass_rate(stdout)}
    rates = parse_pass_rate(stdout)
    pr = rates.get("pass_rate_2")
    if pr is None:
        pr = rates.get("pass_rate_1")
    fallback = {"source": "stdout", "aider_results": None, "reliability": None,
                "note": (f"scored from stdout: no .aider.results.json found under "
                         f"{bench_workdir!r} for run {run_name!r} — reliability columns "
                         f"(well-formed %, output-limit hits, per-case durations) unavailable")}
    if pr is None:  # ran (rc=0) but no pass_rate parsed -> likely an output-format mismatch
        return {**base, **rates, **fallback, "acc": None, "skipped": False,
                "note": "aider ran (rc=0) but no pass_rate_# parsed from stdout — check aider output format"}
    acc = pr / 100.0 if pr > 1.0 else pr   # aider prints percentages (0-100) -> 0-1 fraction
    return {**base, **rates, **fallback, "acc": acc, "skipped": False}

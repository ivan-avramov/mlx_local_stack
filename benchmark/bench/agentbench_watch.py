#!/usr/bin/env python3
"""M54 AgentBench OS watcher daemon (AGENTS.md: every benchmark run is REPORTED AND CRITICALLY
EVALUATED every 5 minutes, by a DAEMON, never by conversational intent). Reads the rows file
`run_agentbench_os.py` is writing and appends a timestamped assessment block to `--out` every
`--interval` seconds, answering the four standing questions, plus a one-line `SUMMARY` for
grepping. Read-only: never perturbs the run, never kills anything.

  nohup .venv-bench/bin/python -m bench.agentbench_watch \
      --rows results/<model>/agentbench_os.v1.jsonl \
      --manifest results/<model>/agentbench_os.v1.manifest.json \
      --total 144 --driver-pid <pid of the run_agentbench_os.py process> \
      --router-log logs/main_model.log \
      --out results/<model>/agentbench_os.v1.watch.log &

Exits when the driver pid is gone (regardless of row count -- 6th cold review round 6 P25/
addendum E: a driver that crashed early must not be watched forever) or rows >= total with the
driver gone, or on SIGTERM.

6th cold review round 6 P25 (HIGH): "the watcher cannot distinguish healthy from not-looking, or
busy from idle." Three fixed mechanisms:
  - Evidence that is MISSING (no rows file, no manifest, no router log, no worker process) is
    reported as `UNKNOWN (evidence missing: ...)`, never silently read as `STALL: none` or
    `WEDGE (idle)` -- those two outcomes now require a POSITIVE, real evidence source, not merely
    the ABSENCE of a stall or a busy signal.
  - Driver pid liveness is checked FIRST, on EVERY tick, independent of the stall threshold
    (addendum E) -- a crashed driver is reported (and the daemon exits) immediately, not only
    once the stall timer eventually fires.
  - Busy/idle during a stall is now an ATTRIBUTABLE signal: the mlx_vlm WORKER process(es) (never
    the :8092 task model) are found via `pgrep -af mlx_vlm.server` and sampled twice 3s apart via
    `ps -o %cpu=` -- BUSY if either sample exceeds 20%, IDLE otherwise, UNKNOWN if no worker
    process is found at all. Non-streaming generation can sit between HTTP requests with no fresh
    completion-log line for a long time while still being genuinely busy, so a log-based busy/idle
    signal (the old `router_recently_active` mechanism) is demoted to a SUPPORTING diagnostic
    field only, never the classifier.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

INTERVAL_DEFAULT_S = 300.0
STALL_DEFAULT_S = 2700.0
ROUTER_ACTIVITY_WINDOW_S = 600.0   # "the last 10 min"
ANSWER_LONG_CHARS = 200
ROUTER_ACTIVITY_MARKER = "/v1/chat/completions"
WORKER_SAMPLE_GAP_S = 3.0
WORKER_BUSY_THRESHOLD_PCT = 20.0
DEGENERATE_EOS_MAX_TOKENS = 5   # P32: finish_reason=="stop" with fewer tokens than this is suspect

# Known-positive self-test fixture (AGENTS.md: "an instrument that cannot distinguish healthy from
# not-looking is worse than none") -- a tiny but representative row set exercising every branch of
# the sanity block (pass/fail, exec_timeout, gold_prepare_differs, varying turns/groups).
SELFTEST_ROWS = [
    {"id": "selftest-1", "group": 1, "passed": True, "outcome": "solved", "turns": 2,
    "answer": "42", "wall_s": 3.0, "wall_total_s": 5.0, "completion_tokens_total": 100,
    "exec_timeout": False, "shell_died": False, "setup_error": False, "converged": True,
    "budget_hits": 0, "gold_prepare": "42", "gold_live": "42", "nonconv_kinds": []},
    {"id": "selftest-2", "group": 1, "passed": False, "outcome": "turn_cap", "turns": 8,
    "answer": None, "wall_s": 20.0, "wall_total_s": 24.0, "completion_tokens_total": 500,
    "exec_timeout": False, "shell_died": False, "setup_error": False, "converged": False,
    "budget_hits": 1, "gold_prepare": None, "gold_live": None, "nonconv_kinds": ["budget_hit"]},
    {"id": "selftest-3", "group": 2, "passed": True, "outcome": "solved", "turns": 1,
    "answer": "42", "wall_s": 2.0, "wall_total_s": 3.0, "completion_tokens_total": 50,
    "exec_timeout": False, "shell_died": False, "setup_error": False, "converged": True,
    "budget_hits": 0, "gold_prepare": "7", "gold_live": "9", "nonconv_kinds": []},
]


# --------------------------------------------------------------------------- I/O (read-only)
def read_rows(path) -> list:
    """Tolerant of a torn final line (the producer may be mid-write at tick time) -- unlike
    run_agentbench_os.read_rows, a malformed NON-final line here is also just skipped: this is a
    read-only observer, not the thing responsible for catching real corruption."""
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def read_manifest(path) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True        # exists, just not ours -- still alive
    except OSError:
        return False
    return True


def run_start_timestamp(manifest: dict):
    """P25: 'time first-item silence from the manifest's started_at' -- the LATEST segment's
    `started_at` (P21: every process start appends one), else provenance.gather's own top-level
    `timestamp`, else None (genuinely unknown, surfaced as evidence-missing, never silently
    treated as 'just started now')."""
    segments = manifest.get("segments") or []
    if segments and isinstance(segments[-1], dict) and segments[-1].get("started_at") is not None:
        return segments[-1]["started_at"]
    return manifest.get("timestamp")


def reference_timestamp(rows: list, manifest: dict, rows_path, stat_fn=None):
    """The timestamp wall-clock staleness is measured FROM: the rows file's own mtime once there
    IS at least one row, else the run's start time (manifest `started_at`) while waiting for the
    FIRST row -- never silently `None` (which `classify_stall` would otherwise read as 'nothing to
    measure, so not stalled')."""
    if rows:
        stat_fn = stat_fn or (lambda p: Path(p).stat())
        try:
            return stat_fn(rows_path).st_mtime
        except OSError:
            return None
    return run_start_timestamp(manifest)


def router_recently_active(router_log_path, window_s: float = ROUTER_ACTIVITY_WINDOW_S,
                           now: float | None = None, tail_bytes: int = 65536) -> bool | None:
    """SUPPORTING DIAGNOSTIC ONLY (P25) -- never the busy/idle classifier (see module docstring).
    True if `router_log_path` was modified within `window_s` of `now` AND its tail contains a
    `/v1/chat/completions` marker; None (unobservable) if the log is missing."""
    now = time.time() if now is None else now
    p = Path(router_log_path)
    if not p.exists():
        return None
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return None
    if now - mtime > window_s:
        return False
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    return ROUTER_ACTIVITY_MARKER in tail


# --------------------------------------------------------------------------- (4) busy/idle (P25)
def _real_pgrep_worker_lines() -> list:
    try:
        proc = subprocess.run(["pgrep", "-af", "mlx_vlm.server"], capture_output=True, text=True,
                             timeout=5)
    except Exception:  # noqa: BLE001
        return []
    return [l for l in (proc.stdout or "").splitlines() if l.strip()]


def find_worker_pids(pgrep_lines_fn=_real_pgrep_worker_lines) -> list:
    """P25: `pgrep -af mlx_vlm.server`, EXCLUDING the :8092 task model (identified by `--port
    8092` on its own cmdline) -- the task model is a SEPARATE, always-resident process and its
    activity says nothing about the run being watched."""
    pids = []
    for line in pgrep_lines_fn():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        pid_str, cmdline = parts
        if "--port 8092" in cmdline:
            continue
        try:
            pids.append(int(pid_str))
        except ValueError:
            continue
    return pids


def _real_ps_cpu_sample(pids: list) -> float:
    if not pids:
        return 0.0
    try:
        proc = subprocess.run(["ps", "-o", "%cpu=", "-p", ",".join(str(p) for p in pids)],
                             capture_output=True, text=True, timeout=5)
    except Exception:  # noqa: BLE001
        return 0.0
    vals = []
    for line in (proc.stdout or "").splitlines():
        try:
            vals.append(float(line.strip()))
        except ValueError:
            continue
    return max(vals) if vals else 0.0


def worker_busy(pgrep_lines_fn=_real_pgrep_worker_lines, sample_fn=_real_ps_cpu_sample,
               sleep_fn=time.sleep, gap_s: float = WORKER_SAMPLE_GAP_S,
               threshold_pct: float = WORKER_BUSY_THRESHOLD_PCT):
    """P25: True (busy) / False (idle) / None (UNKNOWN -- no worker process found at all). Two
    `%cpu` samples `gap_s` apart; either sample over `threshold_pct` counts as busy (a worker
    between requests can legitimately dip to ~0% for a moment while still being in active use)."""
    pids = find_worker_pids(pgrep_lines_fn)
    if not pids:
        return None
    s1 = sample_fn(pids)
    sleep_fn(gap_s)
    s2 = sample_fn(pids)
    return max(s1, s2) > threshold_pct


# --------------------------------------------------------------------------- (1)/(4) stall / wedge
def classify_stall(seconds_since_reference, stall_s: float, driver_pid: int,
                   pid_alive_fn=pid_alive, busy_check_fn=worker_busy) -> str | None:
    """Returns None (genuinely not stalled, driver alive, real reference evidence) or one of
    'DRIVER DEAD' / 'RUNAWAY-SUSPECT (busy)' / 'WEDGE (idle)' /
    'UNKNOWN (evidence missing: ...)'. NEVER returns None or 'WEDGE' when the evidence needed to
    support that conclusion is actually missing (P25).

    Driver liveness is checked FIRST, UNCONDITIONALLY (addendum E) -- independent of the stall
    threshold, so a driver that crashed early (before any stall timer could fire) is reported
    immediately rather than silently read as 'not stalled yet'."""
    if not pid_alive_fn(driver_pid):
        return "DRIVER DEAD"
    if seconds_since_reference is None:
        return "UNKNOWN (evidence missing: no rows file and no run-start reference timestamp)"
    if seconds_since_reference <= stall_s:
        return None
    busy = busy_check_fn() if busy_check_fn is not None else None
    if busy is None:
        return "UNKNOWN (evidence missing: no mlx_vlm worker process found to sample)"
    return "RUNAWAY-SUSPECT (busy)" if busy else "WEDGE (idle)"


# --------------------------------------------------------------------------- (2) rate / ETA
def rate_stats(rows: list) -> dict:
    """P32: `wall_total_s` (container create -> verified removal, the FULL task cost) is the ETA
    basis -- `wall_s` (just the agent loop) understates it; grading/cleanup time is real campaign
    cost. Falls back to `wall_s` only for rows that predate `wall_total_s` (never silently drop
    them from the rate estimate)."""
    totals = [r["wall_total_s"] if isinstance(r.get("wall_total_s"), (int, float))
             else r.get("wall_s")
             for r in rows]
    totals = [t for t in totals if isinstance(t, (int, float))]
    if not totals:
        return {"mean_wall_s": None, "max_wall_s": None}
    return {"mean_wall_s": statistics.mean(totals), "max_wall_s": max(totals)}


def eta_seconds(total: int, done: int, mean_wall_s) -> float | None:
    """ETA from the MEAN, never the median -- AGENTS.md: right-tailed distributions make median
    ETAs flatter by roughly 40%."""
    if mean_wall_s is None:
        return None
    return max(0, total - done) * mean_wall_s


# --------------------------------------------------------------------------- (3) output sanity
def sanity_stats(rows: list) -> dict:
    outcome_counts: dict = {}
    for r in rows:
        outcome_counts[r.get("outcome")] = outcome_counts.get(r.get("outcome"), 0) + 1
    passed = sum(1 for r in rows if r.get("passed") is True)
    failed = sum(1 for r in rows if r.get("passed") is False)
    exec_timeout = sum(1 for r in rows if r.get("exec_timeout"))
    shell_died = sum(1 for r in rows if r.get("shell_died"))
    setup_error = sum(1 for r in rows if r.get("setup_error"))
    # cold-review (prepare rule v2): gold_prepare vs gold_live disagreement is EXPECTED for
    # randomized-init tasks, not necessarily an error -- reported as a count, same spirit as the
    # run_agentbench_os summary's gold_prepare_differs, never as a pass/fail verdict on its own.
    gold_prepare_differs = sum(1 for r in rows if r.get("gold_prepare") is not None
                               and r.get("gold_live") is not None
                               and r["gold_prepare"] != r["gold_live"])
    converged_false = sum(1 for r in rows if r.get("converged") is False)
    budget_hits_total = sum(r.get("budget_hits") or 0 for r in rows)
    # P32: aggregated nonconv_kinds (same shape as run_agentbench_os.summarize's
    # nonconv_kind_counts) and a degenerate-EOS count (finish stop with suspiciously few tokens --
    # a model emitting an immediate EOS is a distinct failure mode from a budget hit or a loop).
    nonconv_kind_counts: dict = {}
    for r in rows:
        for k in (r.get("nonconv_kinds") or []):
            nonconv_kind_counts[k] = nonconv_kind_counts.get(k, 0) + 1
    degenerate_eos = sum(
        1 for r in rows
        if "stop" in (r.get("per_turn_finish_reasons") or [])
        and any(isinstance(c, (int, float)) and c < DEGENERATE_EOS_MAX_TOKENS
               for c in (r.get("per_turn_completion_tokens") or [])))
    turns_histogram: dict = {}
    for r in rows:
        t = r.get("turns")
        if t is not None:
            turns_histogram[t] = turns_histogram.get(t, 0) + 1
    toks = [r["completion_tokens_total"] for r in rows
           if isinstance(r.get("completion_tokens_total"), (int, float))]
    answers = [r.get("answer") for r in rows]
    empty_answers = sum(1 for a in answers if a is None or a == "")
    long_answers = sum(1 for a in answers if isinstance(a, str) and len(a) > ANSWER_LONG_CHARS)
    same_as_previous_answer = sum(
        1 for i in range(1, len(answers))
        if answers[i] is not None and answers[i] != "" and answers[i] == answers[i - 1])
    group_counts: dict = {}
    for r in rows:
        g = r.get("group")
        bucket = group_counts.setdefault(g, [0, 0])   # [passed, total]
        bucket[1] += 1
        if r.get("passed") is True:
            bucket[0] += 1
    per_group_pass_rate = {g: round(p / n, 3) if n else None for g, (p, n) in group_counts.items()}
    return {
        "outcome_counts": outcome_counts, "passed": passed, "failed": failed,
        "exec_timeout": exec_timeout, "shell_died": shell_died, "setup_error": setup_error,
        "gold_prepare_differs": gold_prepare_differs, "converged_false": converged_false,
        "budget_hits_total": budget_hits_total, "nonconv_kind_counts": nonconv_kind_counts,
        "degenerate_eos": degenerate_eos, "turns_histogram": turns_histogram,
        "completion_tokens_mean": round(statistics.mean(toks), 1) if toks else None,
        "completion_tokens_max": max(toks) if toks else None,
        "empty_answers": empty_answers, "long_answers": long_answers,
        "same_as_previous_answer": same_as_previous_answer,
        "per_group_pass_rate": per_group_pass_rate,
    }


# --------------------------------------------------------------------------- assessment block
def build_assessment(rows: list, prev_rows_count: int, total: int, driver_pid: int,
                     router_log_path, stall_s: float, reference_ts, now: float,
                     pid_alive_fn=pid_alive, busy_check_fn=worker_busy,
                     router_active_fn=router_recently_active, label: str = "",
                     rows_evidence: bool = True, manifest_evidence: bool = True,
                     elapsed_s: float | None = None) -> str:
    done = len(rows)
    progressing = done > prev_rows_count
    stats = rate_stats(rows)
    eta = eta_seconds(total, done, stats["mean_wall_s"])
    sanity = sanity_stats(rows)
    seconds_since_reference = None if reference_ts is None else max(0.0, now - reference_ts)
    stall_label = classify_stall(seconds_since_reference, stall_s, driver_pid,
                                 pid_alive_fn, busy_check_fn)
    router_active = router_active_fn(router_log_path, ROUTER_ACTIVITY_WINDOW_S, now)

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    lines = [f"=== M54 agentbench_watch tick {ts}{(' ' + label) if label else ''} ==="]
    # P25: missing/unreadable rows or manifest is EVIDENCE, stated explicitly -- never silently
    # folded into "0 rows, not progressing" with no explanation.
    evidence_notes = []
    if not rows_evidence:
        evidence_notes.append("rows file missing/unreadable")
    if not manifest_evidence:
        evidence_notes.append("manifest missing/unreadable")
    if evidence_notes:
        lines.append(f"(0) EVIDENCE MISSING: {', '.join(evidence_notes)}")
    lines.append(f"(1) PROGRESSING: {'yes' if progressing else 'NO'} -- rows {prev_rows_count} -> "
                f"{done} (of {total} total)")
    mean_s, max_s = stats["mean_wall_s"], stats["max_wall_s"]
    eta_txt = "n/a (no completed rows yet)" if eta is None else f"{eta / 60:.1f} min"
    lines.append(f"(2) RATE: mean_wall_total_s={None if mean_s is None else round(mean_s, 2)} "
                f"max_wall_total_s={max_s} ETA={eta_txt} (from the MEAN wall_total_s, never the "
                "median)")
    # P32: a fixed "CORRECT vs FINISH" line -- remaining ETA vs actual elapsed campaign time, so a
    # reader sees drift between the PREDICTED rate and REALITY at a glance.
    if elapsed_s is not None and eta is not None:
        lines.append(f"    CORRECT-vs-FINISH: elapsed={elapsed_s / 60:.1f} min, "
                    f"predicted-remaining={eta / 60:.1f} min, "
                    f"predicted-total={(elapsed_s + eta) / 60:.1f} min")
    lines.append(
        "(3) SANE: outcome_counts=%s passed=%d failed=%d exec_timeout=%d shell_died=%d "
        "setup_error=%d gold_prepare_differs=%d converged_false=%d budget_hits_total=%d "
        "nonconv_kind_counts=%s degenerate_eos=%d turns_histogram=%s completion_tokens_mean=%s "
        "completion_tokens_max=%s empty_answers=%d long_answers=%d same_as_previous_answer=%d "
        "per_group_pass_rate=%s" % (
            sanity["outcome_counts"], sanity["passed"], sanity["failed"], sanity["exec_timeout"],
            sanity["shell_died"], sanity["setup_error"], sanity["gold_prepare_differs"],
            sanity["converged_false"], sanity["budget_hits_total"], sanity["nonconv_kind_counts"],
            sanity["degenerate_eos"], sanity["turns_histogram"], sanity["completion_tokens_mean"],
            sanity["completion_tokens_max"], sanity["empty_answers"], sanity["long_answers"],
            sanity["same_as_previous_answer"], sanity["per_group_pass_rate"]))
    if stall_label:
        age_txt = "n/a" if seconds_since_reference is None else f"{seconds_since_reference:.0f}s"
        lines.append(f"(4) STALL: {stall_label} -- no new row for {age_txt} "
                    f"(> {stall_s:.0f}s threshold; router-log-recently-active diagnostic="
                    f"{router_active}). NEVER killing anything -- report only.")
    else:
        lines.append(f"(4) STALL: none (driver alive, reference evidence present, "
                    f"router-log-recently-active diagnostic={router_active})")
    block = "\n".join(lines)
    summary = (f"SUMMARY done={done}/{total} progressing={progressing} "
              f"eta_min={'NA' if eta is None else round(eta / 60, 1)} passed={sanity['passed']} "
              f"failed={sanity['failed']} stall={stall_label or 'none'}")
    return block + "\n" + summary + "\n"


# --------------------------------------------------------------------------- self-test (P25: real I/O)
# Known-NEGATIVE fixtures (6th cold review round 6 P25/addendum F): the self-test must exercise
# the REAL file reader + classifier against both known-POSITIVE and known-NEGATIVE cases, written
# to actual temp files, never an in-memory list handed straight to formatting.
_SELFTEST_CASES = (
    "progressing", "stalled-busy", "stalled-idle", "driver-dead", "evidence-missing",
)


def _selftest_case(tmp_dir: Path, case: str, now: float) -> dict:
    """Returns {"ok": bool, "detail": str} after running the REAL read_rows/classify_stall path
    against a fixture written to `tmp_dir`."""
    rows_path = tmp_dir / f"{case}.rows.jsonl"
    manifest_path = tmp_dir / f"{case}.manifest.json"
    if case == "evidence-missing":
        # deliberately do NOT create rows_path or manifest_path
        rows = read_rows(rows_path)
        manifest = read_manifest(manifest_path)
        ref = reference_timestamp(rows, manifest, rows_path)
        label = classify_stall(None if ref is None else max(0.0, now - ref), STALL_DEFAULT_S,
                               os.getpid())
        ok = rows == [] and manifest == {} and label is not None and label.startswith("UNKNOWN")
        return {"ok": ok, "detail": f"rows={rows} manifest={manifest} label={label!r}"}

    manifest_path.write_text(json.dumps({"model": "m", "timestamp": int(now)}), encoding="utf-8")
    manifest = read_manifest(manifest_path)

    if case == "progressing":
        rows_path.write_text(json.dumps(SELFTEST_ROWS[0]) + "\n", encoding="utf-8")
        os.utime(rows_path, (now, now))
        rows = read_rows(rows_path)
        ref = reference_timestamp(rows, manifest, rows_path)
        label = classify_stall(max(0.0, now - ref), STALL_DEFAULT_S, os.getpid())
        ok = len(rows) == 1 and label is None
        return {"ok": ok, "detail": f"rows={len(rows)} label={label!r}"}

    if case in ("stalled-busy", "stalled-idle"):
        rows_path.write_text(json.dumps(SELFTEST_ROWS[0]) + "\n", encoding="utf-8")
        stale = now - (STALL_DEFAULT_S * 2)
        os.utime(rows_path, (stale, stale))
        rows = read_rows(rows_path)
        ref = reference_timestamp(rows, manifest, rows_path)
        busy_fn = (lambda: True) if case == "stalled-busy" else (lambda: False)
        label = classify_stall(max(0.0, now - ref), STALL_DEFAULT_S, os.getpid(),
                               busy_check_fn=busy_fn)
        want = "RUNAWAY-SUSPECT (busy)" if case == "stalled-busy" else "WEDGE (idle)"
        ok = label == want
        return {"ok": ok, "detail": f"rows={len(rows)} label={label!r} want={want!r}"}

    if case == "driver-dead":
        rows_path.write_text(json.dumps(SELFTEST_ROWS[0]) + "\n", encoding="utf-8")
        os.utime(rows_path, (now, now))
        rows = read_rows(rows_path)
        ref = reference_timestamp(rows, manifest, rows_path)
        label = classify_stall(max(0.0, now - ref), STALL_DEFAULT_S, 2 ** 30)  # a pid that can't exist
        ok = label == "DRIVER DEAD"
        return {"ok": ok, "detail": f"label={label!r}"}

    raise ValueError(f"unknown self-test case {case!r}")


def self_test(tmp_dir: Path | None = None, now: float | None = None) -> str:
    """(5) KNOWN-POSITIVE + KNOWN-NEGATIVE SELF-TEST (P25/addendum F): exercises the REAL
    read_rows/read_manifest/classify_stall path against fixtures written to actual files, never
    an in-memory shortcut. Returns the report text; raises SelfTestFailure if ANY case
    misclassifies (the caller refuses to start rather than run unobserved)."""
    import tempfile
    now = time.time() if now is None else now
    owns_tmp = tmp_dir is None
    tmp_dir = Path(tempfile.mkdtemp(prefix="agentbench_watch_selftest_")) if owns_tmp else tmp_dir
    try:
        results = {case: _selftest_case(tmp_dir, case, now) for case in _SELFTEST_CASES}
    finally:
        if owns_tmp:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    lines = ["=== SELF-TEST (known-positive AND known-negative fixtures, real file I/O) ==="]
    all_ok = True
    for case in _SELFTEST_CASES:
        r = results[case]
        all_ok = all_ok and r["ok"]
        lines.append(f"  [{'OK' if r['ok'] else 'FAIL'}] {case}: {r['detail']}")
    bundled_block = build_assessment(SELFTEST_ROWS, prev_rows_count=0, total=len(SELFTEST_ROWS),
                                     driver_pid=os.getpid(), router_log_path="/nonexistent-self-test-path",
                                     stall_s=STALL_DEFAULT_S, reference_ts=now, now=now,
                                     label="[SELF-TEST, bundled 3-row fixture]")
    lines.append(bundled_block)
    text = "\n".join(lines) + "\n"
    if not all_ok:
        raise SelfTestFailure(text)
    return text


class SelfTestFailure(RuntimeError):
    """P25/addendum F: the self-test misclassified at least one known-positive/known-negative
    case -- the daemon REFUSES to start (a monitor that can't pass its own known cases is worse
    than none)."""


# --------------------------------------------------------------------------- CLI / daemon loop
def _append(out_path: Path, text: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(text)
        f.flush()


def run_watch(args) -> int:
    out_path = Path(args.out)
    manifest_path = Path(args.manifest)
    manifest = read_manifest(manifest_path)
    label = f"model={manifest.get('model')}" if manifest.get("model") else ""

    try:
        _append(out_path, self_test())
    except SelfTestFailure as e:
        _append(out_path, str(e))
        print("[agentbench_watch] REFUSED: self-test misclassified a known case -- see the "
             f"SELF-TEST block in {out_path}", file=sys.stderr, flush=True)
        return 2

    stop = {"flag": False}

    def _on_sigterm(signum, frame):
        stop["flag"] = True
    old_handler = signal.signal(signal.SIGTERM, _on_sigterm)

    prev_count = 0
    run_t0 = time.time()
    try:
        while True:
            rows_path = Path(args.rows)
            rows = read_rows(rows_path)
            manifest = read_manifest(manifest_path)
            # P25: evidence presence is tracked explicitly, not inferred from a None reference.
            rows_evidence = rows_path.exists()
            manifest_evidence = manifest_path.exists()
            now = time.time()
            ref = reference_timestamp(rows, manifest, rows_path)
            block = build_assessment(rows, prev_count, args.total, args.driver_pid,
                                     args.router_log, args.stall_s, ref, now, label=label,
                                     rows_evidence=rows_evidence, manifest_evidence=manifest_evidence,
                                     elapsed_s=now - run_t0)
            _append(out_path, block)
            prev_count = len(rows)
            # addendum E: exit after a DRIVER DEAD tick regardless of row count -- a crashed
            # driver is never watched forever waiting for a row count it will now never reach.
            driver_dead = not pid_alive(args.driver_pid)
            done_and_dead = len(rows) >= args.total and driver_dead
            if done_and_dead or driver_dead or stop["flag"] or args.once:
                return 0
            time.sleep(args.interval)
    finally:
        signal.signal(signal.SIGTERM, old_handler)


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rows", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--total", type=int, required=True)
    ap.add_argument("--driver-pid", type=int, required=True)
    ap.add_argument("--router-log", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--interval", type=float, default=INTERVAL_DEFAULT_S)
    ap.add_argument("--stall-s", type=float, default=STALL_DEFAULT_S)
    ap.add_argument("--once", action="store_true", help="tick exactly once and exit (testing)")
    return ap


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    from . import paths
    refusal = paths.confine_path(args.out, what="--out")
    if refusal:
        print(f"[agentbench_watch] REFUSED: {refusal}", file=sys.stderr, flush=True)
        return 2
    return run_watch(args)


if __name__ == "__main__":
    sys.exit(main())

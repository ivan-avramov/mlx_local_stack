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
import re
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
    read-only observer, not the thing responsible for catching real corruption.

    8th cold review round 8 P52(a): a permission-denied or other OS-level read failure (file
    EXISTS but cannot be READ) must not CRASH the watcher daemon -- caught here the same way
    `read_manifest` already catches it, degrading to `[]`. See `_readable()` for how `run_watch`
    distinguishes this from "genuinely no rows yet" to report UNKNOWN rather than silently
    treating an unreadable file as an empty one."""
    p = Path(path)
    if not p.exists():
        return []
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _readable(path) -> bool:
    """P52(a): True only if `path` can actually be OPENED for reading -- `Path.exists()` alone
    says nothing about a permission-denied file, which the watcher must report as UNKNOWN
    evidence, not silently treat as "0 rows so far"."""
    try:
        with open(path, "rb"):
            return True
    except OSError:
        return False


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


# 9th cold review round 9 P12(c): mlx-serve's router log lines (see src/mlx_serve/router.py and
# metrics.py, logger names "mlx-serve.router"/"mlx-serve.metrics") carry NO shared request_id in
# their plain text -- correlation relies on ORDERING: a "POST <endpoint> model=... stream=..."
# line (request received) and a "<endpoint> <status> | model=... | <duration>ms | ..." line
# (request completed). A genuinely IN-FLIGHT request is detected as: the LAST POST line in the
# tail has no matching completion line (same endpoint) AFTER it.
_ROUTER_POST_RE = re.compile(r"POST (\S+) model=")


def _request_in_flight(router_log_path, tail_bytes: int = 65536) -> bool | None:
    """P12(c): True if the router log's LAST POST line has NO matching completion line after it
    (same endpoint) -- a request is genuinely in-flight RIGHT NOW, confirmed from the log, not
    inferred from CPU activity alone. False if the last POST already completed, or no POST was
    seen in the tail at all. None (unobservable) if the log is missing/unreadable."""
    p = Path(router_log_path)
    if not p.exists():
        return None
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    lines = tail.splitlines()
    last_post_idx = None
    last_post_endpoint = None
    for i, line in enumerate(lines):
        m = _ROUTER_POST_RE.search(line)
        if m:
            last_post_idx = i
            last_post_endpoint = m.group(1)
    if last_post_idx is None:
        return False   # no POST in the tail at all -- nothing pending to be in-flight
    completion_marker = re.compile(rf"{re.escape(last_post_endpoint)} \d+ \|")
    for line in lines[last_post_idx + 1:]:
        if completion_marker.search(line):
            return False   # the last POST already has a matching completion line
    return True


# --------------------------------------------------------------------------- (4) busy/idle (P25/P38)
def _real_subprocess_run(argv, timeout: float = 5.0):
    """None on ANY failure (nonzero-launch exception, timeout) -- distinct from a `CompletedProcess`
    with a nonzero returncode, which callers also treat as failure. Never silently coerced into an
    empty/zero result (P38: 'a failed `ps` call returned 0.0, producing WEDGE (idle)')."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except Exception:  # noqa: BLE001
        return None


def find_worker_pids(router_pid, run_fn=_real_subprocess_run) -> list | None:
    """7th cold review round 7 P38 (HIGH), reproduced on this Mac: `pgrep -af mlx_vlm.server`
    returned ONLY the pid, never the command line -- macOS/BSD `pgrep` does not support `-a` as a
    listing flag the way GNU pgrep does, so `-af` silently behaved like a bare `-f` (match-only,
    no output format change) and every line this function tried to parse as "pid cmdline" failed
    silently, discarding every real worker. `pgrep -fl` is BSD's own "long format" flag (pid +
    full argv) and parses correctly.

    Candidates are also now filtered to processes whose PPID CHAIN contains `router_pid` (the
    manifest's own recorded, M50-verified router pid) via `ps -o ppid=` -- this associates the
    worker with THIS run's verified router, not just any mlx_vlm.server process anywhere on the
    box (a stale/unrelated worker from a different experiment must never be sampled).

    Returns None (UNKNOWN) on ANY discovery failure (pgrep launch failure, or an exit code outside
    {0 (matches), 1 (pgrep's own "no match", NOT a failure)}) -- never an empty list silently read
    as "no worker" when discovery itself is actually broken."""
    proc = run_fn(["pgrep", "-fl", "mlx_vlm.server"])
    if proc is None or proc.returncode not in (0, 1):
        return None
    candidates = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        pid_str, cmdline = parts
        if "--port 8092" in cmdline:
            continue
        try:
            candidates.append(int(pid_str))
        except ValueError:
            continue
    if not candidates or router_pid is None:
        return []
    matched = []
    for pid in candidates:
        verdict = _ppid_chain_contains(pid, router_pid, run_fn)
        if verdict is None:
            return None   # a `ps` failure mid-ancestry-walk is a discovery failure, not "no match"
        if verdict:
            matched.append(pid)
    return matched


def _ppid_chain_contains(pid: int, router_pid: int, run_fn, max_depth: int = 12) -> bool | None:
    """True if `router_pid` is an ancestor of `pid` (walking `ps -o ppid=` up to `max_depth`
    hops); False if the chain terminates (init/launchd, pid 1/0, or a cycle) without finding it;
    None (UNKNOWN) if a `ps` call itself fails partway through the walk."""
    cur = pid
    for _ in range(max_depth):
        if cur == router_pid:
            return True
        proc = run_fn(["ps", "-o", "ppid=", "-p", str(cur)])
        if proc is None or proc.returncode != 0:
            return None
        try:
            ppid = int((proc.stdout or "").strip())
        except ValueError:
            return None
        if ppid == router_pid:
            return True
        if ppid in (0, 1, cur):
            return False
        cur = ppid
    return False


def _cpu_sample(pids: list, run_fn) -> float | None:
    """None (UNKNOWN) on failure -- never 0.0, which `worker_busy` would otherwise silently read
    as a genuine idle observation (P38 reproduction)."""
    proc = run_fn(["ps", "-o", "%cpu=", "-p", ",".join(str(p) for p in pids)])
    if proc is None or proc.returncode != 0:
        return None
    vals = []
    for line in (proc.stdout or "").splitlines():
        try:
            vals.append(float(line.strip()))
        except ValueError:
            continue
    return max(vals) if vals else None


def worker_busy(router_pid, run_fn=_real_subprocess_run, sleep_fn=time.sleep,
               gap_s: float = WORKER_SAMPLE_GAP_S, threshold_pct: float = WORKER_BUSY_THRESHOLD_PCT):
    """True (busy) / False (idle) / None (UNKNOWN -- no worker process found, discovery failed, or
    a `ps` sample failed). Two `%cpu` samples `gap_s` apart; either sample over `threshold_pct`
    counts as busy (a worker between requests can legitimately dip to ~0% for a moment while still
    being in active use)."""
    pids = find_worker_pids(router_pid, run_fn)
    if not pids:   # None (discovery failed) or [] (no match) -- both UNKNOWN here
        return None
    s1 = _cpu_sample(pids, run_fn)
    if s1 is None:
        return None
    sleep_fn(gap_s)
    s2 = _cpu_sample(pids, run_fn)
    if s2 is None:
        return None
    return max(s1, s2) > threshold_pct


# --------------------------------------------------------------------------- (1)/(4) stall / wedge
def classify_stall(seconds_since_reference, stall_s: float, driver_pid: int,
                   pid_alive_fn=pid_alive, busy_check_fn=worker_busy,
                   calibrated: bool = True) -> str | None:
    """Returns None (genuinely not stalled, driver alive, real reference evidence) or one of
    'DRIVER DEAD' / 'RUNAWAY-SUSPECT (busy)' / 'WEDGE (idle)' /
    'UNKNOWN (evidence missing: ...)' / 'UNKNOWN (busy-detection not yet calibrated this run...)'.
    NEVER returns None or 'WEDGE' when the evidence needed to support that conclusion is actually
    missing (P25).

    Driver liveness is checked FIRST, UNCONDITIONALLY (addendum E) -- independent of the stall
    threshold, so a driver that crashed early (before any stall timer could fire) is reported
    immediately rather than silently read as 'not stalled yet'.

    8th cold review round 8 P52(d): `calibrated=False` means busy-detection has NEVER actually
    observed a BUSY sample in THIS run -- an idle reading in that state is NOT trustworthy enough
    to label WEDGE (the busy-check mechanism itself could be silently broken: wrong pids, wrong
    port, a %cpu metric that never reads above the threshold on this box -- it would then ALWAYS
    read idle, manufacturing a false kill recommendation every time). The CALLER (`run_watch`)
    is responsible for tracking calibration state across ticks and passing it in; this function
    stays stateless."""
    if not pid_alive_fn(driver_pid):
        return "DRIVER DEAD"
    if seconds_since_reference is None:
        return "UNKNOWN (evidence missing: no rows file and no run-start reference timestamp)"
    if seconds_since_reference <= stall_s:
        return None
    busy = busy_check_fn() if busy_check_fn is not None else None
    if busy is None:
        return "UNKNOWN (evidence missing: no mlx_vlm worker process found to sample)"
    if not busy:
        if not calibrated:
            return ("UNKNOWN (busy-detection not yet calibrated this run -- no BUSY sample "
                    "observed; refusing to label WEDGE on an unproven idle reading)")
        return "WEDGE (idle)"
    return "RUNAWAY-SUSPECT (busy)"


# --------------------------------------------------------------------------- (2) rate / ETA
def rate_stats(rows: list) -> dict:
    """P32: `wall_total_s` (container create -> verified removal, the FULL task cost) is the ETA
    basis -- `wall_s` (just the agent loop) understates it.

    9th cold review round 9 P12(b) (supersedes P32's wall_s fallback): a row LACKING
    `wall_total_s` is now EXCLUDED from the timing arithmetic outright, never silently
    substituted with the SMALLER `wall_s` figure (which understates true campaign cost and would
    quietly bias the mean/ETA downward) -- `excluded_count` is returned so the caller can print
    exactly how many rows were excluded, rather than let the substitution happen invisibly. Never
    raises TypeError regardless of what garbage a row's `wall_total_s` holds (an isinstance guard,
    not a bare arithmetic attempt)."""
    totals = [r.get("wall_total_s") for r in rows if isinstance(r.get("wall_total_s"), (int, float))]
    excluded_count = len(rows) - len(totals)
    if not totals:
        return {"mean_wall_s": None, "max_wall_s": None, "excluded_count": excluded_count}
    return {"mean_wall_s": statistics.mean(totals), "max_wall_s": max(totals),
           "excluded_count": excluded_count}


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
    # 7th cold review round 7 P43(c): PAIR finish_reason with completion_tokens BY TURN (zip),
    # never check "any turn has stop" and "any turn has few tokens" independently -- reproduced:
    # per_turn_finish_reasons=["tool_calls","stop"] with per_turn_completion_tokens=[1,100] used
    # to falsely count as degenerate EOS (turn 1's small token count paired with turn 2's "stop", which
    # itself used 100 tokens and is not degenerate at all).
    def _has_degenerate_eos(r: dict) -> bool:
        frs = r.get("per_turn_finish_reasons") or []
        cts = r.get("per_turn_completion_tokens") or []
        return any(fr == "stop" and isinstance(ct, (int, float)) and ct < DEGENERATE_EOS_MAX_TOKENS
                  for fr, ct in zip(frs, cts))
    degenerate_eos = sum(1 for r in rows if _has_degenerate_eos(r))
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
                     pid_alive_fn=pid_alive, busy_check_fn=None, router_pid=None,
                     router_active_fn=router_recently_active, label: str = "",
                     rows_evidence: bool = True, manifest_evidence: bool = True,
                     elapsed_s: float | None = None, predicted_mean_s: float | None = None,
                     busy_observed_box: dict | None = None,
                     persistence_box: dict | None = None) -> str:
    done = len(rows)
    progressing = done > prev_rows_count
    stats = rate_stats(rows)
    eta = eta_seconds(total, done, stats["mean_wall_s"])
    sanity = sanity_stats(rows)
    seconds_since_reference = None if reference_ts is None else max(0.0, now - reference_ts)
    # P38: the REAL busy/idle path needs `router_pid` to associate a worker with THIS run's
    # verified router (see find_worker_pids) -- a caller-supplied `busy_check_fn` (tests) is used
    # verbatim; otherwise bind the default `worker_busy` to `router_pid` lazily (never called
    # unless classify_stall actually needs a busy/idle verdict).
    raw_busy_check_fn = busy_check_fn if busy_check_fn is not None else (lambda: worker_busy(router_pid))
    # P52(d): `busy_observed_box` (when the caller tracks it -- `run_watch` does, across ticks)
    # records whether a BUSY sample has EVER been seen in this run; `calibrated` reflects state
    # from PRIOR ticks only (this tick's own result, once observed below, updates the box for
    # FUTURE ticks). No box at all (every other build_assessment caller, mostly tests) means
    # "not tracking calibration" -- always treated as calibrated, preserving prior behaviour.
    if busy_observed_box is not None:
        def effective_busy_check_fn():
            result = raw_busy_check_fn()
            if result is True:
                # P12(c): a busy sample only counts toward calibration if it was taken DURING a
                # genuinely in-flight request (confirmed via the router log's last POST having no
                # matching completion line yet) -- otherwise it could be coincidental background
                # CPU activity unrelated to actual request processing, which would wrongly
                # "calibrate" the WEDGE gate on a false signal.
                if _request_in_flight(router_log_path) is True:
                    busy_observed_box["seen"] = True
            return result
        calibrated = busy_observed_box.get("seen", False)
    else:
        effective_busy_check_fn = raw_busy_check_fn
        calibrated = True
    stall_label = classify_stall(seconds_since_reference, stall_s, driver_pid,
                                 pid_alive_fn, effective_busy_check_fn, calibrated=calibrated)
    # 9th cold review round 9 P12: EVIDENCE flags gate the classifier -- a tick that could not
    # even read the rows file or the manifest must never report "STALL: none" (a confident
    # all-clear) on the strength of whatever partial/stale state happened to be left over from a
    # PRIOR tick. This does NOT downgrade an already-positive verdict (DRIVER DEAD is independently
    # verified via pid_alive_fn, unrelated to rows/manifest readability) -- only the "nothing's
    # wrong" conclusion (stall_label is None) is untrustworthy when the evidence behind it is.
    if stall_label is None and not (rows_evidence and manifest_evidence):
        stall_label = ("UNKNOWN (evidence missing/unreadable this tick -- rows and/or manifest "
                       "could not be trusted, so no stall classification can be made)")
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
    # P12(b): rows lacking wall_total_s are EXCLUDED from this arithmetic (never silently
    # substituted with the smaller wall_s) -- the excluded count is always printed so a reader
    # can see exactly how much of `done` the RATE line is actually based on.
    lines.append(f"(2) RATE: mean_wall_total_s={None if mean_s is None else round(mean_s, 2)} "
                f"max_wall_total_s={max_s} ETA={eta_txt} (from the MEAN wall_total_s, never the "
                f"median) excluded_no_wall_total_s={stats['excluded_count']}")
    # 7th cold review round 7 P43(d) + 8th round P54: a REAL "CORRECT vs FINISH" recommendation --
    # the round-6 version only printed elapsed/ETA arithmetic, comparing nothing against a PRIOR
    # prediction and evaluating no actual correction cost. `predicted_mean_s` (--predicted-mean-s,
    # typically the pilot's own observed mean) is compared against the axis's CURRENT observed
    # mean; the TRIGGER fires when the ratio exceeds 2x, more than 30% of graded rows are
    # non-converged, or any of the last 5 rows is a setup_error.
    #
    # P54 (supersedes P43(d)'s single-tick decision): UNKNOWN when there's too little evidence to
    # decide at all (rows < 5, or no --predicted-mean-s given -- nothing to compare against).
    # Otherwise CORRECT ONLY when the trigger has fired on >= 2 CONSECUTIVE blocks (a single bad
    # tick is noise, not a verdict) AND the estimated cost of finishing the remaining work
    # (remaining rows * observed mean) exceeds the cost already SUNK into what's done (done rows *
    # observed mean) -- correcting now is only worth it if there's more expensive work ahead than
    # what would be thrown away. Both cost numbers are printed regardless of the verdict.
    # `persistence_box` (owned by run_watch, one dict for the whole run, across ticks) tracks the
    # trigger's CONSECUTIVE streak; no box at all (every other caller, mostly tests) means no
    # persistence is tracked, so CORRECT can never fire (the safe default).
    nonconv_share = (sanity["converged_false"] / done) if done else None
    last5_setup_error = any(r.get("setup_error") for r in rows[-5:])
    ratio = (mean_s / predicted_mean_s) if (mean_s is not None and predicted_mean_s) else None
    trigger = bool((ratio is not None and ratio > 2.0)
                  or (nonconv_share is not None and nonconv_share > 0.3)
                  or last5_setup_error)
    if done < 5 or not predicted_mean_s:
        recommendation = "UNKNOWN"
        numbers = (f"done={done} (need >=5) predicted_mean_wall_total_s={predicted_mean_s} "
                  "-- not enough evidence to decide")
    else:
        if persistence_box is not None:
            persistence_box["streak"] = persistence_box.get("streak", 0) + 1 if trigger else 0
            streak = persistence_box["streak"]
        else:
            streak = 1 if trigger else 0
        remaining = max(total - done, 0)
        remaining_cost_s = remaining * mean_s
        restart_cost_s = done * mean_s
        correct = bool(streak >= 2 and remaining_cost_s > restart_cost_s)
        recommendation = "CORRECT" if correct else "FINISH"
        numbers = (f"trigger_streak={streak} remaining_cost_s={round(remaining_cost_s, 1)} "
                  f"restart_cost_s={round(restart_cost_s, 1)} "
                  f"ratio={None if ratio is None else round(ratio, 2)} "
                  f"nonconv_share={None if nonconv_share is None else round(nonconv_share, 2)} "
                  f"setup_error_in_last_5={last5_setup_error}")
    lines.append(
        f"    CORRECT-vs-FINISH: observed_mean_wall_total_s={None if mean_s is None else round(mean_s, 2)} "
        f"predicted_mean_wall_total_s={predicted_mean_s} {numbers} -> {recommendation}"
        + (f" (elapsed={elapsed_s / 60:.1f}min predicted-remaining="
           f"{'n/a' if eta is None else f'{eta / 60:.1f}min'})" if elapsed_s is not None else ""))
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
    "progressing", "stalled-busy", "stalled-idle", "stalled-unknown-ps-failure",
    "driver-dead", "evidence-missing",
)
_SELFTEST_ROUTER_PID = 4242
_SELFTEST_WORKER_PID = 5151


class _FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def _selftest_run_fn(cpu_value, ps_fails: bool = False):
    """P38/addendum F: a fake `subprocess.run`-shaped callable returning macOS-style `pgrep -fl`
    output (pid + FULL cmdline, the BSD "long" format -- the format the real bug was in) and `ps`
    output, so the self-test drives `worker_busy`/`find_worker_pids` for REAL rather than
    injecting a `busy_check_fn` boolean directly."""
    def run_fn(argv):
        if argv[:2] == ["pgrep", "-fl"]:
            lines = [f"{_SELFTEST_WORKER_PID} /usr/bin/python3 -m mlx_vlm.server --port 8000",
                    "9999 /usr/bin/python3 -m mlx_vlm.server --port 8092"]   # task model, excluded
            return _FakeCompletedProcess("\n".join(lines) + "\n", 0)
        if argv[:2] == ["ps", "-o"] and "ppid=" in argv[2]:
            # the worker's PPID chain resolves directly to the recorded router pid.
            return _FakeCompletedProcess(f"{_SELFTEST_ROUTER_PID}\n", 0)
        if argv[:2] == ["ps", "-o"] and "%cpu=" in argv[2]:
            if ps_fails:
                return _FakeCompletedProcess("", 1)
            return _FakeCompletedProcess(f"{cpu_value}\n", 0)
        return _FakeCompletedProcess("", 1)
    return run_fn


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

    manifest_path.write_text(json.dumps({"model": "m", "timestamp": int(now),
                                        "router": {"pid": _SELFTEST_ROUTER_PID}}), encoding="utf-8")
    manifest = read_manifest(manifest_path)

    if case == "progressing":
        rows_path.write_text(json.dumps(SELFTEST_ROWS[0]) + "\n", encoding="utf-8")
        os.utime(rows_path, (now, now))
        rows = read_rows(rows_path)
        ref = reference_timestamp(rows, manifest, rows_path)
        label = classify_stall(max(0.0, now - ref), STALL_DEFAULT_S, os.getpid())
        ok = len(rows) == 1 and label is None
        return {"ok": ok, "detail": f"rows={len(rows)} label={label!r}"}

    if case in ("stalled-busy", "stalled-idle", "stalled-unknown-ps-failure"):
        rows_path.write_text(json.dumps(SELFTEST_ROWS[0]) + "\n", encoding="utf-8")
        stale = now - (STALL_DEFAULT_S * 2)
        os.utime(rows_path, (stale, stale))
        rows = read_rows(rows_path)
        ref = reference_timestamp(rows, manifest, rows_path)
        if case == "stalled-busy":
            run_fn, want = _selftest_run_fn(cpu_value=85.0), "RUNAWAY-SUSPECT (busy)"
        elif case == "stalled-idle":
            run_fn, want = _selftest_run_fn(cpu_value=1.0), "WEDGE (idle)"
        else:
            # P38: a failing `ps` (the %cpu sample, not just discovery) must propagate as
            # UNKNOWN -- reproduced bug: a failed `ps` call used to return 0.0, read as idle.
            run_fn, want = _selftest_run_fn(cpu_value=0.0, ps_fails=True), "UNKNOWN"
        busy_fn = lambda: worker_busy(_SELFTEST_ROUTER_PID, run_fn=run_fn, sleep_fn=lambda s: None)
        label = classify_stall(max(0.0, now - ref), STALL_DEFAULT_S, os.getpid(),
                               busy_check_fn=busy_fn)
        ok = (label == want) if case != "stalled-unknown-ps-failure" else bool(
            label and label.startswith("UNKNOWN"))
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
    misclassifies (the caller refuses to start rather than run unobserved).

    7th cold review round 7 P42: when `tmp_dir` isn't supplied (the real/default path), fixture
    files are written under `$STACK_WORKDIR/m54/tmp`, never the bare system temp directory
    (AGENTS.md: no filesystem pollution outside STACK_WORKDIR) -- a caller-supplied `tmp_dir`
    (tests) is used exactly as given."""
    import tempfile
    now = time.time() if now is None else now
    owns_tmp = tmp_dir is None
    if owns_tmp:
        from . import paths
        base = paths.stack_workdir(required=True) / "m54" / "tmp"
        base.mkdir(parents=True, exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="agentbench_watch_selftest_", dir=str(base)))
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
    tick_num = 0
    # P52(d): persists ACROSS ticks (one dict for the whole run) -- see build_assessment's
    # busy_observed_box docstring.
    busy_observed_box: dict = {}
    # P54: persists ACROSS ticks too -- see build_assessment's persistence_box docstring
    # (CORRECT-vs-FINISH trigger streak).
    persistence_box: dict = {}
    calibrate_fn = getattr(args, "calibrate_fn", None) or worker_busy
    try:
        while True:
            tick_num += 1
            rows_path = Path(args.rows)
            rows = read_rows(rows_path)
            manifest = read_manifest(manifest_path)
            # P25: evidence presence is tracked explicitly, not inferred from a None reference.
            # P52(a): existence alone is not enough -- a permission-denied file EXISTS but
            # `read_rows`/`read_manifest` degrade it to [] / {} rather than crash, which would
            # otherwise be indistinguishable from "genuinely no rows yet". `_readable()` catches
            # that case so the tick reports UNKNOWN evidence instead of a false-empty state.
            rows_evidence = rows_path.exists() and _readable(rows_path)
            manifest_evidence = manifest_path.exists() and _readable(manifest_path)
            now = time.time()
            ref = reference_timestamp(rows, manifest, rows_path)
            router_pid = (manifest.get("router") or {}).get("pid")
            if tick_num == 1:
                # P52(c): a PROACTIVE calibration sample on the very first tick, independent of
                # whether a stall is even suspected -- gives the operator early, concrete evidence
                # that busy-detection reads something sane on THIS box/run (ideally sampled while
                # a real request is in flight), rather than discovering only much later (at the
                # first actual stall) whether the mechanism even works.
                if router_pid is None:
                    _append(out_path, "[agentbench_watch] CALIBRATION (tick 1): no router pid "
                                     "recorded in the manifest yet -- cannot sample a worker\n")
                else:
                    calib_sample = calibrate_fn(router_pid)
                    # P12(c): confirm via the router log whether this sample was actually taken
                    # DURING an in-flight request -- only THAT state tells the operator whether
                    # "busy" detection is seeing something real, not background noise.
                    in_flight = _request_in_flight(args.router_log)
                    if calib_sample is True and in_flight is True:
                        busy_observed_box["seen"] = True
                    calibration = {"busy_cpu": calib_sample if in_flight is True else None,
                                  "idle_cpu": calib_sample if in_flight is False else None,
                                  "at": now}
                    _append(out_path, f"[agentbench_watch] CALIBRATION (tick 1): "
                                     f"worker_busy={calib_sample} (router_pid={router_pid}) "
                                     f"in_flight={in_flight} calibration={calibration}\n")
            block = build_assessment(rows, prev_count, args.total, args.driver_pid,
                                     args.router_log, args.stall_s, ref, now, label=label,
                                     router_pid=router_pid,
                                     rows_evidence=rows_evidence, manifest_evidence=manifest_evidence,
                                     elapsed_s=now - run_t0,
                                     predicted_mean_s=getattr(args, "predicted_mean_s", None),
                                     busy_observed_box=busy_observed_box,
                                     persistence_box=persistence_box)
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
    ap.add_argument("--predicted-mean-s", type=float, default=None,
                    help="P43(d): a prior prediction (typically the pilot's own observed mean "
                         "wall_total_s) to compare the axis's CURRENT observed mean against, for "
                         "the CORRECT-vs-FINISH recommendation line.")
    ap.add_argument("--once", action="store_true", help="tick exactly once and exit (testing)")
    ap.add_argument("--calibrate", action="store_true",
                    help="P38: sample the discovered worker's %%cpu for 10s during a KNOWN-ACTIVE "
                         "generation and print it, so the operator can verify busy detection "
                         "independently before trusting a live WEDGE/RUNAWAY-SUSPECT verdict. "
                         "Exits without running the watch loop.")
    return ap


def run_calibrate(args, run_fn=_real_subprocess_run, sleep_fn=time.sleep,
                  duration_s: float = 10.0) -> int:
    """P38: an explicit, operator-driven sanity check -- run this during a generation you KNOW is
    active (e.g. mid-task) and confirm the printed %cpu samples are actually high; run it with no
    generation in flight and confirm they stay near zero. This is the calibration the self-test's
    synthetic fixtures cannot provide (it can't make a real worker busy)."""
    manifest = read_manifest(args.manifest)
    router_pid = (manifest.get("router") or {}).get("pid")
    if router_pid is None:
        print("[agentbench_watch] CALIBRATE: no router pid recorded in the manifest -- cannot "
             "associate a worker with this run", file=sys.stderr)
        return 2
    pids = find_worker_pids(router_pid, run_fn)
    if pids is None:
        print("[agentbench_watch] CALIBRATE: worker DISCOVERY FAILED (pgrep/ps error) -- fix "
             "that before trusting any live busy/idle verdict", file=sys.stderr)
        return 2
    if not pids:
        print(f"[agentbench_watch] CALIBRATE: no worker process found descending from router pid "
             f"{router_pid}", file=sys.stderr)
        return 2
    print(f"[agentbench_watch] CALIBRATE: worker pid(s) {pids}, sampling %cpu every 1s for "
         f"{duration_s:.0f}s...")
    samples = []
    elapsed = 0.0
    while elapsed < duration_s:
        s = _cpu_sample(pids, run_fn)
        samples.append(s)
        print(f"[agentbench_watch] CALIBRATE: t={elapsed:.0f}s %cpu={s}")
        sleep_fn(1.0)
        elapsed += 1.0
    numeric = [s for s in samples if s is not None]
    print(f"[agentbench_watch] CALIBRATE: samples={samples}")
    if not numeric:
        # P52(b): every sample failed (ps error every second of the window) -- this run produced
        # NO evidence at all, never silently "succeed" with nothing to show for it.
        print("[agentbench_watch] CALIBRATE: FAILED -- no valid %cpu sample was obtained in "
             f"{duration_s:.0f}s (every `ps` call failed)", file=sys.stderr)
        return 1
    print(f"[agentbench_watch] CALIBRATE: max={max(numeric):.1f} mean="
         f"{sum(numeric) / len(numeric):.1f} threshold={WORKER_BUSY_THRESHOLD_PCT:.0f}")
    return 0


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    from . import paths
    refusal = paths.confine_path(args.out, what="--out")
    if refusal:
        print(f"[agentbench_watch] REFUSED: {refusal}", file=sys.stderr, flush=True)
        return 2
    if args.calibrate:
        return run_calibrate(args)
    return run_watch(args)


if __name__ == "__main__":
    sys.exit(main())

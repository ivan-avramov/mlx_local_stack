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

Exits when the driver pid is gone AND rows >= total, or on SIGTERM.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import sys
import time
from pathlib import Path

INTERVAL_DEFAULT_S = 300.0
STALL_DEFAULT_S = 2700.0
ROUTER_ACTIVITY_WINDOW_S = 600.0   # "the last 10 min"
ANSWER_LONG_CHARS = 200
ROUTER_ACTIVITY_MARKER = "/v1/chat/completions"

# Known-positive self-test fixture (AGENTS.md: "an instrument that cannot distinguish healthy from
# not-looking is worse than none") -- a tiny but representative row set exercising every branch of
# the sanity block (pass/fail, exec_timeout, gold_prepare_differs, varying turns/groups).
SELFTEST_ROWS = [
    {"id": "selftest-1", "group": 1, "passed": True, "outcome": "solved", "turns": 2,
    "answer": "42", "wall_s": 3.0, "completion_tokens_total": 100, "exec_timeout": False,
    "shell_died": False, "setup_error": False, "converged": True, "budget_hits": 0,
    "gold_prepare": "42", "gold_live": "42"},
    {"id": "selftest-2", "group": 1, "passed": False, "outcome": "turn_cap", "turns": 8,
    "answer": None, "wall_s": 20.0, "completion_tokens_total": 500, "exec_timeout": False,
    "shell_died": False, "setup_error": False, "converged": False, "budget_hits": 1,
    "gold_prepare": None, "gold_live": None},
    {"id": "selftest-3", "group": 2, "passed": True, "outcome": "solved", "turns": 1,
    "answer": "42", "wall_s": 2.0, "completion_tokens_total": 50, "exec_timeout": False,
    "shell_died": False, "setup_error": False, "converged": True, "budget_hits": 0,
    "gold_prepare": "7", "gold_live": "9"},
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


def router_recently_active(router_log_path, window_s: float = ROUTER_ACTIVITY_WINDOW_S,
                           now: float | None = None, tail_bytes: int = 65536) -> bool:
    """True if `router_log_path` was modified within `window_s` of `now` AND its tail contains a
    `/v1/chat/completions` line -- a simple, robust proxy for "the router is actively serving
    requests" that doesn't depend on a specific log timestamp format."""
    now = time.time() if now is None else now
    p = Path(router_log_path)
    if not p.exists():
        return False
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return False
    if now - mtime > window_s:
        return False
    try:
        with open(p, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - tail_bytes))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return False
    return ROUTER_ACTIVITY_MARKER in tail


def classify_stall(seconds_since_last_row, stall_s: float, driver_pid: int, router_log_path,
                   now: float | None = None, pid_alive_fn=pid_alive,
                   router_active_fn=router_recently_active) -> str | None:
    """None if not stalled; else one of RUNAWAY-SUSPECT (busy) / WEDGE (idle) / DRIVER DEAD.
    Never kills anything -- reporting only."""
    if seconds_since_last_row is None or seconds_since_last_row <= stall_s:
        return None
    if not pid_alive_fn(driver_pid):
        return "DRIVER DEAD"
    if router_active_fn(router_log_path, ROUTER_ACTIVITY_WINDOW_S, now):
        return "RUNAWAY-SUSPECT (busy)"
    return "WEDGE (idle)"


# --------------------------------------------------------------------------- (2) rate / ETA
def rate_stats(rows: list) -> dict:
    walls = [r["wall_s"] for r in rows if isinstance(r.get("wall_s"), (int, float))]
    if not walls:
        return {"mean_wall_s": None, "max_wall_s": None}
    return {"mean_wall_s": statistics.mean(walls), "max_wall_s": max(walls)}


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
        "budget_hits_total": budget_hits_total, "turns_histogram": turns_histogram,
        "completion_tokens_mean": round(statistics.mean(toks), 1) if toks else None,
        "completion_tokens_max": max(toks) if toks else None,
        "empty_answers": empty_answers, "long_answers": long_answers,
        "same_as_previous_answer": same_as_previous_answer,
        "per_group_pass_rate": per_group_pass_rate,
    }


# --------------------------------------------------------------------------- assessment block
def build_assessment(rows: list, prev_rows_count: int, total: int, driver_pid: int,
                     router_log_path, stall_s: float, last_row_mtime, now: float,
                     pid_alive_fn=pid_alive, router_active_fn=router_recently_active,
                     label: str = "") -> str:
    done = len(rows)
    progressing = done > prev_rows_count
    stats = rate_stats(rows)
    eta = eta_seconds(total, done, stats["mean_wall_s"])
    sanity = sanity_stats(rows)
    seconds_since_last_row = None if last_row_mtime is None else max(0.0, now - last_row_mtime)
    stall_label = classify_stall(seconds_since_last_row, stall_s, driver_pid, router_log_path,
                                 now, pid_alive_fn, router_active_fn)

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    lines = [f"=== M54 agentbench_watch tick {ts}{(' ' + label) if label else ''} ==="]
    lines.append(f"(1) PROGRESSING: {'yes' if progressing else 'NO'} -- rows {prev_rows_count} -> "
                f"{done} (of {total} total)")
    mean_s, max_s = stats["mean_wall_s"], stats["max_wall_s"]
    eta_txt = "n/a (no completed rows yet)" if eta is None else f"{eta / 60:.1f} min"
    lines.append(f"(2) RATE: mean_wall_s={None if mean_s is None else round(mean_s, 2)} "
                f"max_wall_s={max_s} ETA={eta_txt} (from the MEAN, never the median)")
    lines.append(
        "(3) SANE: outcome_counts=%s passed=%d failed=%d exec_timeout=%d shell_died=%d "
        "setup_error=%d gold_prepare_differs=%d converged_false=%d budget_hits_total=%d "
        "turns_histogram=%s completion_tokens_mean=%s completion_tokens_max=%s empty_answers=%d "
        "long_answers=%d same_as_previous_answer=%d per_group_pass_rate=%s" % (
            sanity["outcome_counts"], sanity["passed"], sanity["failed"], sanity["exec_timeout"],
            sanity["shell_died"], sanity["setup_error"], sanity["gold_prepare_differs"],
            sanity["converged_false"], sanity["budget_hits_total"], sanity["turns_histogram"],
            sanity["completion_tokens_mean"], sanity["completion_tokens_max"],
            sanity["empty_answers"], sanity["long_answers"], sanity["same_as_previous_answer"],
            sanity["per_group_pass_rate"]))
    if stall_label:
        lines.append(f"(4) STALL: {stall_label} -- no new row for "
                     f"{seconds_since_last_row:.0f}s (> {stall_s:.0f}s threshold). "
                     "NEVER killing anything -- report only.")
    else:
        lines.append("(4) STALL: none")
    block = "\n".join(lines)
    summary = (f"SUMMARY done={done}/{total} progressing={progressing} "
              f"eta_min={'NA' if eta is None else round(eta / 60, 1)} passed={sanity['passed']} "
              f"failed={sanity['failed']} stall={stall_label or 'none'}")
    return block + "\n" + summary + "\n"


def self_test(now: float | None = None) -> str:
    """(5) KNOWN-POSITIVE SELF-TEST: parse the bundled fixture and print its assessment. Proves
    the daemon can read rows at all before trusting a live zero (AGENTS.md: "an instrument that
    cannot distinguish healthy from not-looking is worse than none")."""
    now = time.time() if now is None else now
    block = build_assessment(SELFTEST_ROWS, prev_rows_count=0, total=len(SELFTEST_ROWS),
                             driver_pid=os.getpid(), router_log_path="/nonexistent-self-test-path",
                             stall_s=STALL_DEFAULT_S, last_row_mtime=now, now=now,
                             label="[SELF-TEST, bundled fixture]")
    return "=== SELF-TEST (bundled 3-row fixture; proves rows can be read at all) ===\n" + block


# --------------------------------------------------------------------------- CLI / daemon loop
def _append(out_path: Path, text: str) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(text)
        f.flush()


def run_watch(args) -> int:
    out_path = Path(args.out)
    manifest = read_manifest(args.manifest)
    label = f"model={manifest.get('model')}" if manifest.get("model") else ""
    _append(out_path, self_test())

    stop = {"flag": False}

    def _on_sigterm(signum, frame):
        stop["flag"] = True
    old_handler = signal.signal(signal.SIGTERM, _on_sigterm)

    prev_count = 0
    try:
        while True:
            rows_path = Path(args.rows)
            rows = read_rows(rows_path)
            last_mtime = rows_path.stat().st_mtime if rows_path.exists() else None
            now = time.time()
            block = build_assessment(rows, prev_count, args.total, args.driver_pid,
                                     args.router_log, args.stall_s, last_mtime, now, label=label)
            _append(out_path, block)
            prev_count = len(rows)
            done_and_dead = len(rows) >= args.total and not pid_alive(args.driver_pid)
            if done_and_dead or stop["flag"] or args.once:
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
    return run_watch(args)


if __name__ == "__main__":
    sys.exit(main())

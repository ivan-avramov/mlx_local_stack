"""A work-queue runner, so a finished job never means an idle worker.

The queue is a JSON list of ``{"name": ..., "cmd": ...}`` entries in a FILE. A runner on the worker
box executes them in order and writes each outcome back into the same file.

WHY A FILE AND A DAEMON, rather than an agent launching jobs. An agent only executes when the
operator messages it, so every job completion is an idle gap until someone notices. AGENTS.md already
records this for monitoring — "THE CADENCE MUST LIVE IN A DAEMON, NOT IN THE CONVERSATION" — and it
applies identically to launching work. Measured 2026-08-14: generation finished at 07:43 and the box
sat idle for hours with an unblocked job already identified and waiting.

Design decisions, each with a reason and a test:

- **The queue file is the durable state.** The runner does not survive a reboot; the file does, and
  it is committed, so the operator can reorder or append without touching the runner. It is also the
  answer to "what has this box actually done?" — the question the scp-drift episode showed is
  otherwise unanswerable.
- **A failing job does not stop the queue.** On a single-worker campaign an unattended stop costs
  hours.
- **A failed job is never retried automatically.** A job that failed once usually fails again, and a
  retry loop is how a box spends a night achieving nothing. Re-queueing is an explicit operator act
  (clear the entry's ``state``).
- **The queue is re-read before every entry**, so work can be appended mid-run.
- **Entries are shell commands, not a DSL.** Everything worth queueing is already a committed CLI
  invocation; a job schema would only re-encode it.
- **Operator control is three files, checked BETWEEN items, never mid-item.** A running job is
  never interrupted -- the runner only consults ``STOP``/``SKIP``/``PAUSE`` at the same boundary
  it already re-reads the queue at, and each file is CONSUMED (deleted) once acted on so the next
  launch starts fresh. ``STOP`` finishes the current item then exits; ``SKIP`` marks the next
  pending item skipped and moves on; ``PAUSE`` waits (polling) until removed. Precedence when
  several are dropped at once: STOP > SKIP > PAUSE. Default location
  ``<repo>/benchmark/control/``, or ``$STACK_WORKDIR/control/`` when that out-of-repo workdir is
  set (see ``docs/PLAN.md``) -- a file, not the committed queue, because pause/stop/skip are
  transient operator acts, not plan edits.

Usage on the worker (detached, survives the ssh session):

    nohup .venv-bench/bin/python -m bench.workqueue docs/work-queue.json \\
        --log /tmp/workqueue.log >/dev/null 2>&1 &

    touch benchmark/control/PAUSE   # or $STACK_WORKDIR/control/PAUSE
"""
import argparse
import json
import os
import re
import subprocess
import time
from pathlib import Path

from . import paths

# Backstop: a malformed queue must not spin forever.
DEFAULT_MAX_JOBS = 200
DEFAULT_POLL_INTERVAL = 30


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _load(path: Path) -> list:
    try:
        data = json.loads(Path(path).read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _save(path: Path, entries: list) -> None:
    Path(path).write_text(json.dumps(entries, indent=1))


def _safe_name(name: str) -> str:
    """A filesystem-safe log basename. Job names are human-written and carry spaces, slashes,
    commas and `=` (e.g. "livecodebench n=100 all four servable models")."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "job").strip())[:70].strip("_") or "job"


def _shell(cmd: str, logfile=None) -> int:
    """Run a job, capturing stdout AND stderr to `logfile`.

    Capturing is not optional. Found on first live use: with output discarded, a `generate` job's
    driver output — per-chunk progress and ETAs, provenance CLEANED/RESTAMPED lines, and the reason
    for any failure — went nowhere, leaving only an exit code. An exit code cannot answer "why did
    that fail", and on a single-worker campaign re-running a job to see its output costs hours.
    """
    if logfile is None:
        return subprocess.run(cmd, shell=True).returncode
    with open(logfile, "a", buffering=1) as fh:
        fh.write(f"===== {_now()} $ {cmd}\n")
        return subprocess.run(cmd, shell=True, stdout=fh, stderr=subprocess.STDOUT).returncode


TERMINAL = ("done", "failed", "skipped")


def _load_state(state_path, plan: list) -> dict:
    """Runtime state, keyed by job NAME, from a file SEPARATE from the plan.

    Separate because the plan is COMMITTED CONFIG: writing state into it makes the plan permanent
    drift on the worker box, stops a reordered plan being synced via git without colliding with
    state, and makes the plan un-editable from the driver box. Found live 2026-08-14.

    Keyed by NAME, not index, so the operator can REORDER the plan freely — reordering is their main
    lever for getting data sooner, and index-keying would silently mis-attribute outcomes.

    Inline state from the original design is MIGRATED rather than ignored, so an already-completed
    job is never re-run (a redone `generate` is hours of worker time).
    """
    st = {}
    if state_path and Path(state_path).exists():
        try:
            loaded = json.loads(Path(state_path).read_text())
            if isinstance(loaded, dict):
                st = loaded
        except (json.JSONDecodeError, OSError):
            st = {}
    for e in plan:                                  # migrate legacy inline state
        n = e.get("name")
        if n and n not in st and e.get("state"):
            st[n] = {k: e[k] for k in ("state", "exit_code", "started_at", "finished_at", "note")
                     if k in e}
    return st


def _save_state(state_path, st: dict) -> None:
    if state_path:
        Path(state_path).write_text(json.dumps(st, indent=1, sort_keys=True))


def _is_pending(e: dict, st: dict) -> bool:
    """True if this entry has not yet reached a TERMINAL state (done/failed/skipped)."""
    rec = st.get(e.get("name")) or {}
    if rec.get("state") in TERMINAL:
        return False
    if e.get("state") in TERMINAL and not st:
        return False
    return True


def _next_index(entries: list, st: dict = None):
    """First entry with no terminal state. `failed` is terminal — see the no-auto-retry rule."""
    st = st or {}
    for i, e in enumerate(entries):
        if _is_pending(e, st):
            return i
    return None


def _pending_count(entries: list, st: dict = None) -> int:
    """How many entries `_next_index` would still work through — what a STOP reports as
    'remaining'."""
    st = st or {}
    return sum(1 for e in entries if _is_pending(e, st))


def _control_dir(override=None) -> Path:
    """Where the operator drops STOP/SKIP/PAUSE files, checked BETWEEN queue items.

    `$STACK_WORKDIR/control` when the worker's out-of-repo workdir is set (see docs/PLAN.md),
    else `<repo>/benchmark/control`. A file, not the committed queue, because pausing/stopping/
    skipping are transient operator acts, not plan edits — the queue stays reorderable and
    git-syncable regardless of whether the worker is currently paused.
    """
    if override is not None:
        return Path(override)
    workdir = os.environ.get("STACK_WORKDIR")
    if workdir:
        return Path(workdir) / "control"
    return paths.repo_root() / "benchmark" / "control"


def _consume(path: Path) -> None:
    """Delete a control file once acted on, so the next launch starts fresh. Missing is fine —
    another process may have already cleared it."""
    try:
        path.unlink()
    except OSError:
        pass


def _check_control(cdir: Path, *, entries: list, st: dict, queue_path, state_path, log,
                    poll_interval: float) -> str:
    """Act on operator control files between items. Returns ``"stop"`` (caller must exit the
    loop), ``"skipped"`` (an item was marked skipped; caller should re-read and continue), or
    ``""`` (nothing to do, proceed to the next item).

    Precedence when several files exist at once: STOP > SKIP > PAUSE — checked in that order every
    time, so an operator dropping STOP need not first clear a SKIP or PAUSE they left earlier.
    """
    stop_path, skip_path, pause_path = cdir / "STOP", cdir / "SKIP", cdir / "PAUSE"

    if stop_path.exists():
        remaining = _pending_count(entries, st)
        log(f"[workqueue] STOP requested: exiting with {remaining} item(s) remaining")
        _consume(stop_path)
        return "stop"

    if skip_path.exists():
        idx = _next_index(entries, st)
        _consume(skip_path)
        if idx is None:
            log("[workqueue] SKIP requested but the queue has nothing pending; ignored")
            return ""
        entry = entries[idx]
        name = entry.get("name") or f"job-{idx}"
        outcome = {"state": "skipped", "note": "operator SKIP", "finished_at": _now()}
        if state_path:
            st[name] = {**(st.get(name) or {}), **outcome}
            _save_state(state_path, st)
        else:
            entries[idx].update(**outcome)
            _save(queue_path, entries)
        log(f"[workqueue] SKIP {name!r}: operator SKIP")
        return "skipped"

    if pause_path.exists():
        log(f"[workqueue] PAUSE: waiting for operator (polling every {poll_interval}s)")
        while pause_path.exists():
            time.sleep(poll_interval)
        log("[workqueue] PAUSE lifted: resuming")
        return ""

    return ""


def run(queue_path, *, runner=None, max_jobs: int = DEFAULT_MAX_JOBS, log=print, logdir=None,
        state_path=None, control_dir=None, poll_interval: float = DEFAULT_POLL_INTERVAL) -> int:
    """Execute queued entries in order until none remain. Returns the number of jobs run.

    `control_dir` defaults to `_control_dir()` (see there); pass an explicit path in tests so a
    run never consults the real operator control directory. `poll_interval` (seconds) governs the
    PAUSE poll — injectable so tests never sleep the real 30s.
    """
    queue_path = Path(queue_path)
    logdir = Path(logdir) if logdir else None
    if logdir:
        logdir.mkdir(parents=True, exist_ok=True)
    cdir = Path(control_dir) if control_dir is not None else _control_dir()
    cdir.mkdir(parents=True, exist_ok=True)      # lazy: only created once a run actually starts
    ran = 0
    while ran < max_jobs:
        entries = _load(queue_path)             # re-read: work can be appended mid-run
        st = _load_state(state_path, entries)
        signal = _check_control(cdir, entries=entries, st=st, queue_path=queue_path,
                                 state_path=state_path, log=log, poll_interval=poll_interval)
        if signal == "stop":
            break
        if signal == "skipped":
            continue                            # re-read; proceed to the following item
        idx = _next_index(entries, st)
        if idx is None:
            break
        entry = entries[idx]
        name = entry.get("name") or f"job-{idx}"
        cmd = entry.get("cmd")
        if not cmd:
            if state_path:
                st[name] = {"state": "failed", "note": "entry has no 'cmd'", "finished_at": _now()}
                _save_state(state_path, st)
            else:
                entry.update(state="failed", note="entry has no 'cmd'", finished_at=_now())
                _save(queue_path, entries)
            log(f"[workqueue] SKIP {name!r}: no 'cmd'")
            continue                            # malformed != crash the queue
        jobfile = None
        if logdir:
            jobfile = logdir / f"{_safe_name(name)}.joblog"
        if state_path:
            st[name] = {"state": "running", "started_at": _now(),
                        **({"log": jobfile.name} if jobfile else {})}
            _save_state(state_path, st)
        else:
            if jobfile:
                entry["log"] = jobfile.name
            entry.update(state="running", started_at=_now())
            _save(queue_path, entries)
        log(f"[workqueue] START {entry.get('name')!r}: {cmd}")
        try:
            rc = (runner(cmd) if runner is not None
                  else _shell(cmd, logfile=jobfile))
        except Exception as e:                  # noqa: BLE001 — a runner crash is a job failure
            rc, note = 1, f"{type(e).__name__}: {str(e)[:120]}"
        else:
            note = None
        outcome = {"state": "done" if rc == 0 else "failed", "exit_code": rc,
                   "finished_at": _now()}
        if jobfile is not None:
            outcome["log"] = jobfile.name
        if note:
            outcome["note"] = note
        if state_path:
            # Re-read state: nothing else writes it, but be consistent about not clobbering.
            st = _load_state(state_path, entries)
            st[name] = {**(st.get(name) or {}), **outcome}
            _save_state(state_path, st)
        else:
            entries = _load(queue_path)         # operator may have appended while this ran
            if idx < len(entries):
                entries[idx].update(**outcome)
                _save(queue_path, entries)
        log(f"[workqueue] {'DONE' if rc == 0 else 'FAILED'} {name!r} rc={rc}")
        ran += 1
    log(f"[workqueue] queue drained after {ran} job(s)")
    return ran


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queue", help="path to the queue JSON file")
    ap.add_argument("--log", default=None, help="append progress here (default: stdout)")
    ap.add_argument("--max-jobs", type=int, default=DEFAULT_MAX_JOBS)
    ap.add_argument("--state", default=None,
                    help="runtime state file, keyed by job name (RECOMMENDED: keeps the committed "
                         "plan untouched so it can be reordered and synced via git)")
    ap.add_argument("--logdir", default=None,
                    help="directory for per-job output logs (default: alongside --log)")
    ap.add_argument("--control-dir", default=None,
                    help="where STOP/SKIP/PAUSE are checked, between items (default: "
                         "$STACK_WORKDIR/control if set, else <repo>/benchmark/control)")
    ap.add_argument("--poll-interval", type=float, default=DEFAULT_POLL_INTERVAL,
                    help="seconds between PAUSE checks while paused (default: 30)")
    args = ap.parse_args(argv)

    if args.log:
        fh = open(args.log, "a", buffering=1)                      # noqa: SIM115 — daemon lifetime

        def log(msg):
            fh.write(f"{_now()} {msg}\n")
    else:
        log = print
    run(args.queue, max_jobs=args.max_jobs, log=log, state_path=args.state,
        logdir=args.logdir or (Path(args.log).parent if args.log else None),
        control_dir=args.control_dir, poll_interval=args.poll_interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
  several are dropped at once: STOP > SKIP > PAUSE. ``SKIP`` may name a specific job
  (``echo <job-id> > SKIP``) to skip that job even when it is not next-pending; an empty/blank
  ``SKIP`` file falls back to skipping whichever job is next-pending. Default location
  ``<repo>/benchmark/control/``, or ``$STACK_WORKDIR/control/`` when that out-of-repo workdir is
  set (see ``docs/PLAN.md``) -- a file, not the committed queue, because pause/stop/skip are
  transient operator acts, not plan edits.
- **A per-item watcher** answers AGENTS.md's "report + critically evaluate every 5 minutes" rule
  without depending on the driving agent being awake. An entry that carries a ``"watch"`` dict
  (``{"model", "bench", "total", "driver_pattern", "interval"?}``) gets its own
  ``benchmark/m1/bench_watch.py`` subprocess for the duration of that item, writing ticks to
  ``<status_dir>/watch_<model>_<bench>.md``; it is started right before the item runs and reaped
  (terminate, then wait/kill) in a ``finally`` so it never outlives the item -- success, failure,
  or a runner exception all reap it the same way. An entry with no ``"watch"`` key gets no
  watcher (e.g. an archive/grade job). Status dir defaults to ``$STACK_WORKDIR/status`` when set,
  else ``<repo>/benchmark/status`` (gitignored).
- **The status aggregator** (``python -m bench.workqueue <queue> --aggregate``) is the ONLY writer
  of ``<status_dir>/current.md``: one compact table -- item / state / last watcher line /
  timestamp -- built by reading the queue, its state file, and every ``watch_*.md`` already on
  disk. It never runs a job and never touches a watcher process, so it carries none of the
  concurrent-writer hazard a live watcher tick would.

Usage on the worker (detached, survives the ssh session):

    nohup .venv-bench/bin/python -m bench.workqueue docs/work-queue.json \\
        --log /tmp/workqueue.log >/dev/null 2>&1 &

    touch benchmark/control/PAUSE            # or $STACK_WORKDIR/control/PAUSE
    touch benchmark/control/STOP
    echo <job-id> > benchmark/control/SKIP   # skip that job specifically; blank file = next-pending
"""
import argparse
import json
import os
import re
import subprocess
import sys
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


def _status_dir(override=None) -> Path:
    """Where per-item watcher output and ``current.md`` live.

    Same resolution rule as ``_control_dir``: ``$STACK_WORKDIR/status`` when the out-of-repo
    workdir is set, else ``<repo>/benchmark/status`` (gitignored — this is runtime state, not
    committed config).
    """
    if override is not None:
        return Path(override)
    workdir = os.environ.get("STACK_WORKDIR")
    if workdir:
        return Path(workdir) / "status"
    return paths.repo_root() / "benchmark" / "status"


def _watcher_cmd(watch: dict, status_dir: Path) -> list:
    """Build the ``bench_watch.py`` argv for one queue item's ``"watch"`` dict.

    Raises ``KeyError`` if a required key (``model``/``bench``/``total``/``driver_pattern``) is
    missing — the caller turns that into a logged SKIP rather than a crashed queue, the same
    tolerance already applied to a malformed ``"cmd"``.
    """
    model, bench, total = watch["model"], watch["bench"], watch["total"]
    pattern = watch["driver_pattern"]
    interval = watch.get("interval", 300)
    out = Path(status_dir) / f"watch_{model}_{bench}.md"
    script = paths.repo_root() / "benchmark" / "m1" / "bench_watch.py"
    return [sys.executable, str(script),
            "--models", model, "--bench", bench, "--total", str(total),
            "--driver-pattern", pattern, "--out", str(out), "--interval", str(interval)]


def _default_spawn(cmd: list):
    """Real subprocess launch, used when the caller injects no ``spawn_watcher``. Going through
    ``subprocess.Popen`` (not a bare call) keeps it mockable via ``monkeypatch`` on
    ``workqueue.subprocess.Popen`` without requiring every caller to inject a fake."""
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL)


def _reap_watcher(proc, log, name: str) -> None:
    """Stop a per-item watcher no matter how the item ended. Called from a ``finally`` so a
    watcher is never left running past its item — success, failure, and a runner exception all
    reap it identically. Terminate first (clean exit, the watcher just appends one more tick at
    most); fall back to kill if it does not exit within the wait."""
    try:
        proc.terminate()
    except Exception:                               # noqa: BLE001 — terminate() itself failed;
        try:                                         # the process may already be gone, or refusing
            proc.kill()                              # a clean signal — go straight to kill().
        except Exception:                            # noqa: BLE001
            pass
        log(f"[workqueue] watcher stopped for {name!r}")
        return
    try:
        proc.wait(timeout=5)
    except Exception:                               # noqa: BLE001 — didn't exit within the wait
        try:
            proc.kill()
        except Exception:                           # noqa: BLE001
            pass
    log(f"[workqueue] watcher stopped for {name!r}")


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
        target = skip_path.read_text(errors="replace").strip()
        _consume(skip_path)
        if target:
            # Targeted form: 'echo <job-id> > SKIP' -- skips that job specifically, even when it
            # is not the next-pending one, so a stuck job can be dropped without first waiting
            # out everything queued ahead of it.
            idx = next((i for i, e in enumerate(entries)
                       if e.get("name") == target and _is_pending(e, st)), None)
            if idx is None:
                log(f"[workqueue] SKIP requested for {target!r} but it is not a pending job; ignored")
                return ""
            note = f"operator SKIP {target}"
        else:
            idx = _next_index(entries, st)
            if idx is None:
                log("[workqueue] SKIP requested but the queue has nothing pending; ignored")
                return ""
            note = "operator SKIP"
        entry = entries[idx]
        name = entry.get("name") or f"job-{idx}"
        outcome = {"state": "skipped", "note": note, "finished_at": _now()}
        if state_path:
            st[name] = {**(st.get(name) or {}), **outcome}
            _save_state(state_path, st)
        else:
            entries[idx].update(**outcome)
            _save(queue_path, entries)
        log(f"[workqueue] SKIP {name!r}: {note}")
        return "skipped"

    if pause_path.exists():
        log(f"[workqueue] PAUSE: waiting for operator (polling every {poll_interval}s)")
        while pause_path.exists():
            time.sleep(poll_interval)
        log("[workqueue] PAUSE lifted: resuming")
        return ""

    return ""


def run(queue_path, *, runner=None, max_jobs: int = DEFAULT_MAX_JOBS, log=print, logdir=None,
        state_path=None, control_dir=None, poll_interval: float = DEFAULT_POLL_INTERVAL,
        status_dir=None, spawn_watcher=None) -> int:
    """Execute queued entries in order until none remain. Returns the number of jobs run.

    `control_dir` defaults to `_control_dir()` (see there); pass an explicit path in tests so a
    run never consults the real operator control directory. `poll_interval` (seconds) governs the
    PAUSE poll — injectable so tests never sleep the real 30s.

    `status_dir` defaults to `_status_dir()` (see there). `spawn_watcher` defaults to
    `_default_spawn` (a real `subprocess.Popen`); inject a fake in tests so a run never spawns a
    real `bench_watch.py` process. Only entries carrying a `"watch"` dict get a watcher.
    """
    queue_path = Path(queue_path)
    logdir = Path(logdir) if logdir else None
    if logdir:
        logdir.mkdir(parents=True, exist_ok=True)
    cdir = Path(control_dir) if control_dir is not None else _control_dir()
    cdir.mkdir(parents=True, exist_ok=True)      # lazy: only created once a run actually starts
    sdir = Path(status_dir) if status_dir is not None else _status_dir()
    spawn_fn = spawn_watcher if spawn_watcher is not None else _default_spawn
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
        watch = entry.get("watch")
        proc = None
        if watch:
            sdir.mkdir(parents=True, exist_ok=True)  # lazy: only created once a watcher is due
            try:
                wcmd = _watcher_cmd(watch, sdir)
            except KeyError as e:
                log(f"[workqueue] watcher SKIPPED for {name!r}: 'watch' missing key {e}")
            else:
                try:
                    proc = spawn_fn(wcmd)
                    log(f"[workqueue] watcher started for {name!r}")
                except Exception as e:          # noqa: BLE001 — a dead watcher must not fail the item
                    log(f"[workqueue] watcher spawn FAILED for {name!r}: "
                        f"{type(e).__name__}: {e}")
        log(f"[workqueue] START {entry.get('name')!r}: {cmd}")
        try:
            rc = (runner(cmd) if runner is not None
                  else _shell(cmd, logfile=jobfile))
        except Exception as e:                  # noqa: BLE001 — a runner crash is a job failure
            rc, note = 1, f"{type(e).__name__}: {str(e)[:120]}"
        else:
            note = None
        finally:
            if proc is not None:                # reaped on EVERY exit path, including the raise above
                _reap_watcher(proc, log, name)
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


def _watcher_tail(status_dir: Path, watch) -> tuple:
    """Last non-blank line of one item's watcher file, plus the file's mtime as an ISO timestamp.

    Returns ``("-", "-")`` when the item never got a watcher (no `"watch"` dict, e.g. an
    archive/grade job) or the watcher hasn't written its first tick yet — both are normal states,
    not errors.
    """
    if not watch:
        return "-", "-"
    model, bench = watch.get("model"), watch.get("bench")
    if not model or not bench:
        return "-", "-"
    f = Path(status_dir) / f"watch_{model}_{bench}.md"
    if not f.exists():
        return "-", "-"
    nonblank = [ln for ln in f.read_text(errors="replace").splitlines() if ln.strip()]
    last = nonblank[-1] if nonblank else "-"
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime))
    return last, ts


def aggregate(queue_path, *, status_dir=None, state_path=None) -> str:
    """Build the operator's one-page status table and write it to `<status_dir>/current.md`.

    THE ONLY WRITER of `current.md` — nothing else in this module touches that filename, so
    repeated `--aggregate` invocations (the only intended caller) simply overwrite it wholesale.
    There is no concurrent-writer hazard to guard against because there is no second writer: the
    live watcher subprocesses write only their own `watch_<model>_<bench>.md`, never this file.

    Reads (never runs) the queue, its state file, and whatever `watch_*.md` files already exist —
    so it is safe to call at any time, including against a queue that is currently running.
    """
    sdir = Path(status_dir) if status_dir is not None else _status_dir()
    entries = _load(queue_path)
    st = _load_state(state_path, entries)
    lines = [f"<!-- generated by `python -m bench.workqueue --aggregate` at {_now()} -->", "",
             "| item | state | last watcher line | timestamp |", "|---|---|---|---|"]
    for e in entries:
        name = e.get("name") or "?"
        rec = st.get(name) or {}
        state = rec.get("state") or e.get("state") or "pending"
        last_line, ts = _watcher_tail(sdir, e.get("watch"))
        last_line = (last_line or "-").replace("|", "\\|")
        lines.append(f"| {name} | {state} | {last_line} | {ts} |")
    text = "\n".join(lines) + "\n"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "current.md").write_text(text)
    return text


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
    ap.add_argument("--status-dir", default=None,
                    help="where per-item watcher output and current.md live (default: "
                         "$STACK_WORKDIR/status if set, else <repo>/benchmark/status)")
    ap.add_argument("--aggregate", action="store_true",
                    help="write <status_dir>/current.md from the queue/state and existing "
                         "watch_*.md files, then exit without running any jobs")
    args = ap.parse_args(argv)

    if args.aggregate:
        aggregate(args.queue, status_dir=args.status_dir, state_path=args.state)
        return 0

    if args.log:
        fh = open(args.log, "a", buffering=1)                      # noqa: SIM115 — daemon lifetime

        def log(msg):
            fh.write(f"{_now()} {msg}\n")
    else:
        log = print
    run(args.queue, max_jobs=args.max_jobs, log=log, state_path=args.state,
        logdir=args.logdir or (Path(args.log).parent if args.log else None),
        control_dir=args.control_dir, poll_interval=args.poll_interval,
        status_dir=args.status_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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

Usage on the worker (detached, survives the ssh session):

    nohup .venv-bench/bin/python -m bench.workqueue docs/work-queue.json \\
        --log /tmp/workqueue.log >/dev/null 2>&1 &
"""
import argparse
import json
import re
import subprocess
import time
from pathlib import Path

# Backstop: a malformed queue must not spin forever.
DEFAULT_MAX_JOBS = 200


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


def _next_index(entries: list):
    """First entry with no terminal state. `failed` is terminal — see the no-auto-retry rule."""
    for i, e in enumerate(entries):
        if e.get("state") in (None, "", "queued"):
            return i
    return None


def run(queue_path, *, runner=None, max_jobs: int = DEFAULT_MAX_JOBS, log=print, logdir=None) -> int:
    """Execute queued entries in order until none remain. Returns the number of jobs run."""
    queue_path = Path(queue_path)
    logdir = Path(logdir) if logdir else None
    if logdir:
        logdir.mkdir(parents=True, exist_ok=True)
    ran = 0
    while ran < max_jobs:
        entries = _load(queue_path)             # re-read: work can be appended mid-run
        idx = _next_index(entries)
        if idx is None:
            break
        entry = entries[idx]
        cmd = entry.get("cmd")
        if not cmd:
            entry.update(state="failed", note="entry has no 'cmd'", finished_at=_now())
            _save(queue_path, entries)
            log(f"[workqueue] SKIP {entry.get('name')!r}: no 'cmd'")
            continue                            # malformed != crash the queue
        jobfile = None
        if logdir:
            jobfile = logdir / f"{idx:02d}-{_safe_name(entry.get('name'))}.joblog"
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
        # Re-read before writing back: the operator may have appended while this job ran.
        entries = _load(queue_path)
        if idx < len(entries):
            entries[idx].update(state="done" if rc == 0 else "failed", exit_code=rc,
                                finished_at=_now())
            if jobfile is not None:
                entries[idx]["log"] = jobfile.name
            if note:
                entries[idx]["note"] = note
            _save(queue_path, entries)
        log(f"[workqueue] {'DONE' if rc == 0 else 'FAILED'} {entry.get('name')!r} rc={rc}")
        ran += 1
    log(f"[workqueue] queue drained after {ran} job(s)")
    return ran


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("queue", help="path to the queue JSON file")
    ap.add_argument("--log", default=None, help="append progress here (default: stdout)")
    ap.add_argument("--max-jobs", type=int, default=DEFAULT_MAX_JOBS)
    ap.add_argument("--logdir", default=None,
                    help="directory for per-job output logs (default: alongside --log)")
    args = ap.parse_args(argv)

    if args.log:
        fh = open(args.log, "a", buffering=1)                      # noqa: SIM115 — daemon lifetime

        def log(msg):
            fh.write(f"{_now()} {msg}\n")
    else:
        log = print
    run(args.queue, max_jobs=args.max_jobs, log=log,
        logdir=args.logdir or (Path(args.log).parent if args.log else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

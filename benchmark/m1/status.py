"""Read-only, one-screen status: what the work queue and its per-item watchers say RIGHT NOW.

WHY THIS EXISTS, separate from `bench.workqueue --aggregate`. That writer already builds a
markdown table -- one row per queue item, its state, and its watcher's last line -- but it does so
as a scheduled side effect of the daemon, into a FILE meant for `tail -f`. This script is the
complementary case: an operator (or another agent) at a terminal asking "what's going on right
now", who wants a compact human-readable answer immediately, without needing to know the daemon's
internals, wait for its next write, or even have it running. It touches nothing -- no daemon, no
writes, safe against a queue that is mid-run.

Reads two things:
  - `docs/work-queue.json` (or `--queue`): the plan, for queue state counts. Schema-agnostic --
    it only ever needs a `state` field per entry (defaulting to "pending"), so it works whether
    the file is the executable `{"name", "cmd", ...}` form `bench.workqueue` runs, or a plan-table
    mirror like the current `docs/work-queue.json` (`{"id", "description", "state", ...}`).
  - `watch_*.md` files already on disk under the status dir (default `$STACK_WORKDIR/status`,
    else `<repo>/benchmark/status`) -- the same per-item watcher output `bench.workqueue` spawns
    via `bench_watch.py`. For each, only the LAST tick block is shown: the file's own most recent
    PROGRESS/RATE/OUTPUT/CORRECTION lines, so a long-running watch reads as "where it is now", not
    "where it started". `current.md` (workqueue's own aggregate output) is deliberately excluded --
    it is not a per-item watcher, and echoing it back would double the same information under a
    different label.

Usage:
    PYTHONPATH=benchmark .venv-bench/bin/python benchmark/m1/status.py
    PYTHONPATH=benchmark .venv-bench/bin/python benchmark/m1/status.py --queue docs/work-queue.json \\
        --status-dir /path/to/status
"""
import argparse
import json
import os
from pathlib import Path

from bench import paths


def _default_queue_path() -> Path:
    return paths.repo_root() / "docs" / "work-queue.json"


def _default_status_dir() -> Path:
    """Same resolution rule as `bench.workqueue._status_dir`: `$STACK_WORKDIR/status` when the
    out-of-repo workdir is set, else `<repo>/benchmark/status`."""
    workdir = os.environ.get("STACK_WORKDIR")
    if workdir:
        return Path(workdir) / "status"
    return paths.repo_root() / "benchmark" / "status"


def _load_queue(path) -> list:
    """Tolerant like `bench.workqueue._load`: a missing or malformed file reads as an empty
    queue, never a crash -- this tool must stay usable even against a half-written file."""
    try:
        data = json.loads(Path(path).read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def queue_state_counts(entries: list) -> dict:
    counts = {}
    for e in entries:
        state = e.get("state") or "pending"
        counts[state] = counts.get(state, 0) + 1
    return counts


def _last_tick_block(text: str) -> list:
    """The last `===== ... =====`-headed block in a watcher file, i.e. its most recent tick.
    No header found (empty file, or a tick still being written) -> whatever lines exist."""
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.startswith("=====")]
    return lines[starts[-1]:] if starts else lines


def _line_containing(lines: list, marker: str) -> str:
    return next((ln.strip() for ln in lines if marker in ln), "-")


def summarize_watch_file(path: Path) -> dict:
    """The last tick of one watcher file: header (driver alive/gone + timestamp) plus its
    PROGRESS/RATE/OUTPUT/CORRECTION lines, matching the four questions `bench_watch.py` answers
    every tick."""
    text = path.read_text(errors="replace")
    block = _last_tick_block(text)
    header = block[0].strip("= ").strip() if block else "(no ticks yet)"
    return {
        "name": path.stem,
        "header": header,
        "progress": _line_containing(block, "PROGRESS"),
        "rate": _line_containing(block, "RATE"),
        "output": _line_containing(block, "OUTPUT"),
        "correction": _line_containing(block, "CORRECTION"),
    }


def _watch_files(status_dir: Path) -> list:
    """`watch_*.md` -- the filename `bench.workqueue._watcher_cmd` gives every per-item watcher
    it spawns. Excludes `current.md` (the workqueue aggregator's own output, not a watcher)."""
    if not Path(status_dir).exists():
        return []
    return sorted(Path(status_dir).glob("watch_*.md"))


def render(queue_path, status_dir) -> str:
    """Build the one-screen text summary. Pure and read-only -- callers print it, never this
    function; safe to call repeatedly against a live run."""
    entries = _load_queue(queue_path)
    counts = queue_state_counts(entries)
    lines = [f"=== bench work-queue status ({queue_path}) ===",
             f"{len(entries)} item(s)" + (":" if counts else "")]
    for state in sorted(counts):
        lines.append(f"  {state}: {counts[state]}")
    lines.append("")

    files = _watch_files(status_dir)
    lines.append(f"=== watchers ({status_dir}) ===")
    if not files:
        lines.append("  no watcher files found")
        return "\n".join(lines) + "\n"

    for f in files:
        s = summarize_watch_file(f)
        lines.append(f"  [{s['name']}] {s['header']}")
        lines.append(f"    {s['progress']}")
        lines.append(f"    {s['rate']}")
        lines.append(f"    {s['output']}")
        lines.append(f"    {s['correction']}")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queue", default=None, help="path to the queue JSON file "
                    "(default: <repo>/docs/work-queue.json)")
    ap.add_argument("--status-dir", default=None, help="directory holding watch_*.md files "
                    "(default: $STACK_WORKDIR/status if set, else <repo>/benchmark/status)")
    args = ap.parse_args(argv)

    queue_path = Path(args.queue) if args.queue else _default_queue_path()
    status_dir = Path(args.status_dir) if args.status_dir else _default_status_dir()
    print(render(queue_path, status_dir), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

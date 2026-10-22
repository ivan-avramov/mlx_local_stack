"""P444: the leg wrapper's B5 watcher, run for REAL (no mock) — `benchmark/m1/bench_watch.py` launched by `_watcher_for` must
import `bench`, tick while the driver lives and stop cleanly; a watcher that dies at start fails the leg before the driver runs.
(Wave-1 attempt 2: every leg's watcher died with `ModuleNotFoundError: No module named 'bench'`, speed invalid on every leg.)"""

import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import p426_leg as L
from bench import paths

REPO = paths.repo_root()


def _spec(tmp_path):
    rows = tmp_path / "rows.jsonl"
    rows.write_text('{"id": "a"}\n')
    return SimpleNamespace(name="math500-p426-off-smoke", model="Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed",
                           kind="rows", rows_path=rows)


def test_the_real_watcher_imports_bench_ticks_and_stops(tmp_path):
    """The driver is the watcher's PARENT (the leg process), as in production — macOS `pgrep` excludes its own ancestors, so
    a pattern probe from the watcher never sees the leg (Wave-1 attempt 3: `driver=GONE` at the first tick)."""
    start = L._watcher_for(REPO, 5, tmp_path, interval_s=1.0)
    stop = start(_spec(tmp_path))
    time.sleep(3.5)
    watch = stop()
    log = (tmp_path / "math500-p426-off-smoke.watch.log").read_text()
    assert "driver=ALIVE" in log
    assert watch["exited_early"] is False and watch["ticks"] >= 2
    assert L.watch_problems(watch, "2026-10-22 10:00:00", "2026-10-22 10:00:04") in ([], [
        f"watcher power failure at {(watch['power_failure'] or {}).get('first_failure_at')}"])


def test_a_watcher_that_dies_at_start_raises_before_the_driver_runs(tmp_path):
    broken = tmp_path / "repo"
    (broken / "benchmark" / "m1").mkdir(parents=True)
    (broken / "benchmark" / "m1" / "bench_watch.py").write_text("raise SystemExit('boom')\n")
    (broken / ".venv-bench" / "bin").mkdir(parents=True)
    (broken / ".venv-bench" / "bin" / "python").symlink_to(sys.executable)
    start = L._watcher_for(broken, 5, tmp_path, interval_s=1.0, startup_s=2.0)
    with pytest.raises(RuntimeError, match="watcher exited at start"):
        start(_spec(tmp_path))



def test_bench_watch_tracks_a_driver_pid_and_stops_when_it_exits(tmp_path):
    """`--driver-pid` (exact, ancestor-safe): ALIVE while the pid lives, a final GONE tick and exit 0 after it dies."""
    drv = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
    rows = tmp_path / "rows.jsonl"
    rows.write_text("")
    out = tmp_path / "w.log"
    rc = subprocess.run([sys.executable, str(REPO / "benchmark/m1/bench_watch.py"), "--models", "m", "--bench", "rows",
                         "--total", "1", "--driver-pid", str(drv.pid), "--out", str(out), "--rows-file", str(rows),
                         "--interval", "1"], env={**__import__("os").environ, "PYTHONPATH": str(REPO / "benchmark")},
                        timeout=30).returncode
    drv.wait()
    log = out.read_text()
    assert rc == 0 and "driver=ALIVE" in log and "DRIVER EXITED" in log

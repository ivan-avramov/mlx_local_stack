"""P444: the leg wrapper's B5 watcher, run for REAL (no mock) — `benchmark/m1/bench_watch.py` launched by `_watcher_for` must
import `bench`, tick while the driver lives and stop cleanly; a watcher that dies at start fails the leg before the driver runs.
(Wave-1 attempt 2: every leg's watcher died with `ModuleNotFoundError: No module named 'bench'`, speed invalid on every leg.)"""

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import p426_leg as L
from bench import paths

REPO = paths.repo_root()


@pytest.fixture
def driver():
    """A stand-in driver whose command line carries a unique pattern for the watcher's liveness probe."""
    tag = f"p426-watch-test-{uuid.uuid4().hex[:8]}"
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", tag])
    yield tag
    proc.kill()
    proc.wait()


def _spec(tmp_path):
    rows = tmp_path / "rows.jsonl"
    rows.write_text('{"id": "a"}\n')
    return SimpleNamespace(name="math500-p426-off-smoke", model="Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed",
                           kind="rows", rows_path=rows)


def test_the_real_watcher_imports_bench_ticks_and_stops(tmp_path, driver):
    start = L._watcher_for(REPO, 5, tmp_path, driver_pattern=driver, interval_s=1.0)
    stop = start(_spec(tmp_path))
    time.sleep(3.5)
    watch = stop()
    log = (tmp_path / "math500-p426-off-smoke.watch.log").read_text()
    assert "driver=ALIVE" in log
    assert watch["exited_early"] is False and watch["ticks"] >= 2
    assert L.watch_problems(watch, "2026-10-22 10:00:00", "2026-10-22 10:00:04") in ([], [
        f"watcher power failure at {(watch['power_failure'] or {}).get('first_failure_at')}"])


def test_a_watcher_that_dies_at_start_raises_before_the_driver_runs(tmp_path, driver, monkeypatch):
    broken = tmp_path / "repo"
    (broken / "benchmark" / "m1").mkdir(parents=True)
    (broken / "benchmark" / "m1" / "bench_watch.py").write_text("raise SystemExit('boom')\n")
    (broken / ".venv-bench" / "bin").mkdir(parents=True)
    (broken / ".venv-bench" / "bin" / "python").symlink_to(sys.executable)
    start = L._watcher_for(broken, 5, tmp_path, driver_pattern=driver, interval_s=1.0, startup_s=2.0)
    with pytest.raises(RuntimeError, match="watcher exited at start"):
        start(_spec(tmp_path))


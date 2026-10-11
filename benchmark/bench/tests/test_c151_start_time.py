"""C151 (2026-10-11): psutil's `create_time()` is not a stable process identity in a long-lived process on macOS.

psutil 7.x `_psosx.adjust_proc_create_time` adds `INIT_BOOT_TIME - boot_time()` to every `create_time()` once the two
differ by >= 1 s, and `boot_time()` is whole seconds, so a sub-second wall-clock correction that carries
`kern.boottime` across a second boundary shifts every later read by 1 s. C147 V3 attempt 1 aborted on it (probe
"worker identity missing or drifted", driver "not the recorded router identity", same PIDs). Identity sites must use
the unadjusted kernel start time; these tests shift `INIT_BOOT_TIME` by 1 s to emulate the correction."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from bench import chain_ops, proc_guard, tg1_runner

psutil = pytest.importorskip("psutil")
pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="psutil boot-time adjustment is the macOS path")

BENCH = Path(__file__).resolve().parents[1]


@pytest.fixture
def boot_shift(monkeypatch):
    from psutil import _psosx

    def shift(seconds=1.0):
        monkeypatch.setattr(_psosx, "INIT_BOOT_TIME", _psosx.INIT_BOOT_TIME - seconds)
    return shift


@pytest.fixture
def child():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield p
    p.kill()
    p.wait()


def test_the_adjustment_is_real_on_this_psutil(boot_shift, child):
    # Guards the premise: if psutil stops adjusting, this fails and C151's helper can be revisited.
    before = psutil.Process(child.pid).create_time()
    boot_shift()
    assert psutil.Process(child.pid).create_time() == pytest.approx(before + 1.0)


def test_start_time_ignores_a_boot_time_shift(boot_shift, child):
    before = proc_guard.start_time(psutil.Process(child.pid))
    boot_shift()
    assert proc_guard.start_time(psutil.Process(child.pid)) == before


def test_start_time_equals_the_unshifted_create_time(child):
    # Values already recorded in manifests came from unshifted reads; the helper must reproduce them exactly.
    assert proc_guard.start_time(psutil.Process(child.pid)) == psutil.Process(child.pid).create_time()


def test_start_time_falls_back_for_objects_without_a_psutil_impl():
    class Fake:
        def create_time(self):
            return 123.5
    assert proc_guard.start_time(Fake()) == 123.5


def test_chain_ops_identities_ignore_a_boot_time_shift(boot_shift, child):
    ct, chain = chain_ops.default_create_time(child.pid), chain_ops.default_parents(child.pid)
    boot_shift()
    assert chain_ops.default_create_time(child.pid) == ct
    assert chain_ops.default_parents(child.pid) == chain


def test_tg1_worker_identity_survives_a_boot_time_shift(boot_shift, child, monkeypatch, tmp_path):
    reg = tmp_path / "registry.yaml"
    reg.write_text("mlx_port: 8091\n")
    monkeypatch.setattr(tg1_runner.provenance.paths, "registry_path", lambda: reg)

    class Probe:
        @staticmethod
        def _worker_load_identity(model, router):
            return {"pid": child.pid, "model_path": "org/model"}

    before = tg1_runner.worker_identity(Probe, "m", {"pid": os.getpid()})
    boot_shift()
    after = tg1_runner.worker_identity(Probe, "m", {"pid": os.getpid()})
    proc_guard.require_identity(before, after)          # raised "worker identity missing or drifted" before C151


def test_process_guard_identity_survives_a_boot_time_shift(boot_shift, child, tmp_path):
    g = proc_guard.ProcessGuard(roots=[tmp_path], protected_pids=())
    g.started = 0.0                                      # the child predates the guard; only identity is under test
    created = proc_guard.start_time(psutil.Process(child.pid))
    boot_shift()
    assert g._same_identity(child.pid, created)


def test_no_raw_create_time_reads_at_identity_sites():
    src = {name: (BENCH / name).read_text() for name in ("chain_ops.py", "proc_guard.py", "tg1_runner.py")}
    hits = [f"{n}:{i}" for n, t in src.items() for i, line in enumerate(t.splitlines(), 1)
            if re.search(r"\.create_time\(\)", line) and "def start_time" not in line
            and "return proc.create_time()" not in line]
    assert not hits, "raw create_time() at identity sites (use proc_guard.start_time): " + ", ".join(hits)

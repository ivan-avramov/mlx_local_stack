"""M72 probe idle-GPU gate (S20-P1 / C313): refuse a measured pass on a busy GPU, as the power gate refuses bad power."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "spikes"))
import m72_gates as G  # noqa: E402

IOREG_IDLE = '+-o AGXAcceleratorG17X  <class AGXAcceleratorG17X>\n    "PerformanceStatistics" = {"In use system memory"=1,"Device Utilization %"=0,"Renderer Utilization %"=0}\n'
IOREG_BUSY = IOREG_IDLE.replace('"Device Utilization %"=0', '"Device Utilization %"=100')


def _run(stdout):
    def fake(argv, **kw):
        assert argv[0] == "ioreg"
        return subprocess.CompletedProcess(argv, 0, stdout=stdout, stderr="")
    return fake


def test_utilization_parsed(monkeypatch):
    monkeypatch.setattr(G.subprocess, "run", _run(IOREG_BUSY))
    assert G.gpu_utilization() == 100
    monkeypatch.setattr(G.subprocess, "run", _run(IOREG_IDLE))
    assert G.gpu_utilization() == 0


def test_utilization_unreadable_is_none(monkeypatch):
    monkeypatch.setattr(G.subprocess, "run", _run(""))
    assert G.gpu_utilization() is None

    def boom(argv, **kw):
        raise OSError("no ioreg")
    monkeypatch.setattr(G.subprocess, "run", boom)
    assert G.gpu_utilization() is None


@pytest.mark.parametrize("util,floor,ok", [
    (0, 0.17, True),        # session 20 after the reboot
    (5, 0.49, True),        # at the limits
    (100, 1.0, False),      # session 20 morning: stuck-busy GPU
    (100, 0.17, False),     # busy, fast floor
    (0, 1.0, False),        # idle reading, slow floor
    (None, 0.17, False),    # unreadable utilization is a stop
    (0, None, False),       # unmeasured floor is a stop
])
def test_idle_ok(util, floor, ok):
    assert G.gpu_idle_ok({"device_utilization_pct": util, "tiny_op_floor_ms": floor}) is ok


def test_floor_is_median_of_timed_round_trips():
    ticks = iter([0.0, 0.001, 1.0, 1.0002, 2.0, 2.0003])  # 1.0, 0.2, 0.3 ms
    assert G.tiny_op_floor_ms(lambda: None, n=3, clock=lambda: next(ticks)) == pytest.approx(0.3)


def test_probe_refuses_on_busy_gpu():
    src = (Path(__file__).resolve().parents[2] / "spikes" / "m72_tq4_probe.py").read_text()
    main = src[src.index("def main():"):]
    gate = main.index("gpu_idle_ok(")
    assert main.index("power_ok(p0)") < gate < main.index("mx.random.seed(72)")  # before any measured work
    assert "sys.exit(5)" in main[gate:gate + 400]
    assert '"gpu_idle_start"' in main

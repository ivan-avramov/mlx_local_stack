"""P371 review r2 F12: the chain always executes `repo / ArmBinding.probe` (the resolved repo-relative entry frozen in the
config), never the raw `--probe` path: a symlink retargeted after init launches nothing outside the frozen closure."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from bench.tests.m64_support import FAP_PATH, M, REPO, SMOKE
from bench.tests.test_c147_chain_runner import C147, CHAIN, FakeOps, R


@pytest.fixture
def link():
    path = C147 / "_r2_link_probe.py"
    path.unlink(missing_ok=True)
    os.symlink(C147 / "fake_probe.py", path)
    yield path
    path.unlink(missing_ok=True)


def test_tg1_executes_the_resolved_entry_not_a_retargeted_symlink(link, tmp_path):
    a = R.parse_args(CHAIN + ["--probe", str(link), "--out-root", str(tmp_path / "o")])
    chain = R.Chain(a, FakeOps(tmp_path), R.Timers(), lambda m: None, R.load_universe(), tmp_path / "o", {})
    frozen = REPO / chain.config.arms[0].probe
    assert frozen == C147 / "fake_probe.py"
    link.unlink()
    os.symlink(C147 / "drive_chain.sh", link)                       # retargeted after init: other code
    assert chain.probe_of(chain.arm.arm) == frozen and chain.probe == frozen


def test_m64_executes_the_resolved_entry_not_a_retargeted_symlink(link, tmp_path):
    from bench.tests.m64_support import FakeOps as MOps
    link.unlink()
    os.symlink(FAP_PATH, link)
    a = M.parse_args(SMOKE + ["--probe", f"oc={link}", "--out-root", str(tmp_path / "o")])
    chain = M.build_chain(a, MOps(tmp_path), M.Timers(), lambda m: None, {"python": ["a"], "go": ["b"]},
                          tmp_path / "o", {})
    frozen = REPO / chain.config.arms[0].probe
    assert frozen == FAP_PATH
    link.unlink()
    os.symlink(C147 / "drive_chain.sh", link)
    assert chain.probe_of("oc") == frozen

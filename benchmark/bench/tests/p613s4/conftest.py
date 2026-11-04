"""P613 step-4 test fixtures. The golden module is marked `p613s4_golden` (registered here).

World A / B (see `s4world`) are built once per session and are READ-ONLY; `clone_a` / `clone_b` give a writable copy.
"""
from __future__ import annotations

import importlib
import shutil

import pytest

from bench.tests.p613s3 import s3world as S
from bench.tests.p613s3 import sigview as SV
from bench.tests.p613s4 import s4world as W


def pytest_configure(config):
    config.addinivalue_line("markers", "p613s4_golden: golden numbers on the committed benchmark/results data (P613 step 4)")


@pytest.fixture(scope="session")
def world_a(tmp_path_factory):
    return W.build_case(tmp_path_factory.mktemp("s4worldA"), "A")


@pytest.fixture(scope="session")
def world_b(tmp_path_factory):
    return W.build_case(tmp_path_factory.mktemp("s4worldB"), "B")


@pytest.fixture(scope="session")
def cli_a(tmp_path_factory):
    """World A without the rejected key: the one `p426_signals all` accepts."""
    return W.build_case(tmp_path_factory.mktemp("s4cliA"), "A", with_rejected=False)


@pytest.fixture(scope="session")
def cli_b(tmp_path_factory):
    return W.build_case(tmp_path_factory.mktemp("s4cliB"), "B", with_rejected=False)


def _clone(case, tmp_path):
    dst = tmp_path / f"copy{len(list(tmp_path.glob('copy*')))}"
    shutil.copytree(case.base, dst, symlinks=True)
    return S.A7Case.attach(dst)


@pytest.fixture
def clone_a(world_a, tmp_path):
    return lambda: _clone(world_a, tmp_path)


@pytest.fixture
def clone_b(world_b, tmp_path):
    return lambda: _clone(world_b, tmp_path)


@pytest.fixture
def clone_cli_a(cli_a, tmp_path):
    return lambda: _clone(cli_a, tmp_path)


def _panel(case, tmp_path_factory, name):
    """An exported + judged panel for the case (step-3 CLI), so `all --panel` runs."""
    from bench import p426_panel

    out = tmp_path_factory.mktemp(name) / "panel"
    proc = case.export(out)
    assert proc.returncode == 0, proc.stderr[-800:]
    SV.write_verdicts(out, {**SV.PLAN_S1, **SV.PLAN_S2_ON}, p426_panel)
    return out


@pytest.fixture(scope="session")
def panel_a(cli_a, tmp_path_factory):
    return _panel(cli_a, tmp_path_factory, "s4panelA")


@pytest.fixture(scope="session")
def panel_b(cli_b, tmp_path_factory):
    return _panel(cli_b, tmp_path_factory, "s4panelB")


@pytest.fixture(scope="session")
def divmod_():
    """The module holding `a7_divergence` (contract: `bench/p426_signals.py` or a new `bench/p426_signals_divergence.py`).
    Imported lazily so a missing interface fails each test rather than the collection."""
    for name in ("bench.p426_signals_divergence", "bench.p426_signals"):
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        if hasattr(mod, "a7_divergence"):
            return mod
    pytest.fail("no module defines `a7_divergence` (looked in bench.p426_signals_divergence and bench.p426_signals)")


@pytest.fixture(scope="session")
def verify():
    return importlib.import_module("bench.p426_verify")

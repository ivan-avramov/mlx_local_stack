"""P613 step-3 test fixtures. The golden module is marked `p613s3_golden` (registered here)."""
from __future__ import annotations

import importlib
import shutil

import pytest

from bench.tests.p613s3 import s3world as S


def pytest_configure(config):
    config.addinivalue_line("markers", "p613s3_golden: golden numbers on the committed benchmark/results data (P613 step 3)")


@pytest.fixture(scope="module")
def panel():
    """`bench.p426_panel` imported lazily so a missing interface fails each test, not the whole collection."""
    return importlib.import_module("bench.p426_panel")


@pytest.fixture
def verify():
    return importlib.import_module("bench.p426_verify")


@pytest.fixture(scope="module")
def a7(tmp_path_factory):
    """The hermetic A7 case (module scope, treat as READ-ONLY; use `clone` for a mutation): world + B8 + evidence commit +
    exercises + universe + judges file."""
    base = tmp_path_factory.mktemp("a7case")
    return S.A7Case(base)


@pytest.fixture
def clone(a7, tmp_path):
    """clone() -> a writable copy of the A7 case under tmp_path (same relative layout; evidence commit lives in the copy's git)."""
    def _clone():
        dst = tmp_path / f"copy{len(list(tmp_path.glob('copy*')))}"
        shutil.copytree(a7.base, dst, symlinks=True)
        return S.A7Case.attach(dst)
    return _clone


@pytest.fixture(scope="module")
def exported(a7, tmp_path_factory):
    """One successful `a7-export` of the module A7 case: (case, out_dir, completed process)."""
    out = tmp_path_factory.mktemp("exp") / "panel"
    proc = a7.export(out)
    return a7, out, proc

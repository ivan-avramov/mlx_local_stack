"""P613 step-1 test fixtures. The golden module is marked `p613_golden` (registered here)."""
from __future__ import annotations

import importlib
import json

import pytest

from bench.tests.p613 import a7world


def pytest_configure(config):
    config.addinivalue_line("markers", "p613_golden: golden numbers on the committed benchmark/results/p426 data (P613 step 1)")


@pytest.fixture
def verify():
    """`bench.p426_verify` imported lazily so a missing module fails each test, not the whole collection."""
    return importlib.import_module("bench.p426_verify")


@pytest.fixture
def signals():
    return importlib.import_module("bench.p426_signals")


@pytest.fixture
def make_world(tmp_path):
    """make_world(**spec) -> a7world.World under tmp_path (one world per call; later calls get their own subdirectory)."""
    count = []

    def _make(**spec):
        count.append(1)
        return a7world.World(tmp_path / f"w{len(count)}", **spec)
    return _make


@pytest.fixture
def pipeline(verify, signals, make_world):
    """pipeline(**spec) -> (world, b8, sig): build a world, run B8, then compute the A7 signals from the accepted pairs."""
    def _run(**spec):
        w = make_world(**spec)
        b8 = verify.verify_a7(w.root)
        sig = signals.compute_a7(w.root, b8)
        return w, b8, sig
    return _run


def dump_json(doc) -> str:
    return json.dumps(doc, sort_keys=True, indent=1, default=str)

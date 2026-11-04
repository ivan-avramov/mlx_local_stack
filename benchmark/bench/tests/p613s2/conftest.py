"""P613 step-2 test fixtures. The golden module is marked `p613s2_golden` (registered here)."""
from __future__ import annotations

import importlib

import pytest

from bench.tests.p613s2 import wave1world as WW


def pytest_configure(config):
    config.addinivalue_line("markers", "p613s2_golden: golden numbers on the committed benchmark/results data (P613 step 2)")


@pytest.fixture
def verify():
    """`bench.p426_verify` imported lazily so a missing interface fails each test, not the whole collection."""
    return importlib.import_module("bench.p426_verify")


@pytest.fixture
def signals():
    return importlib.import_module("bench.p426_signals")


@pytest.fixture
def make_w1(tmp_path, monkeypatch):
    """make_w1(**spec) -> Wave1World (one per call, own subdirectory; `generate.RESULTS` points at the latest world)."""
    count = []

    def _make(**spec):
        count.append(1)
        return WW.Wave1World(tmp_path / f"w{len(count)}", monkeypatch, **spec)
    return _make


@pytest.fixture
def wave1(verify, make_w1):
    """wave1(**spec) -> (world, verify_wave1 result)."""
    def _run(**spec):
        w = make_w1(**spec)
        return w, verify.verify_wave1(w.p426, w.rows_root, w.repo)
    return _run


@pytest.fixture(scope="module")
def scenario(tmp_path_factory):
    """scenario(name, **spec) -> (world, b8, sig), computed once per module and name (A7 world included). Called inside the
    test body, so a missing interface fails the test (the exception is cached and re-raised)."""
    cache = {}

    def build(name, **spec):
        if name not in cache:
            try:
                with pytest.MonkeyPatch.context() as mp:
                    verify = importlib.import_module("bench.p426_verify")
                    signals = importlib.import_module("bench.p426_signals")
                    spec.setdefault("with_a7", True)
                    w = WW.Wave1World(tmp_path_factory.mktemp(name), mp, **spec)
                    b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
                    sig = signals.compute_all(w.p426, w.rows_root, b8, b8_sha256="ab" * 32)
                    cache[name] = (w, b8, sig)
            except BaseException as exc:      # noqa: BLE001 - cached so every test of the module fails the same way
                cache[name] = exc
        out = cache[name]
        if isinstance(out, BaseException):
            raise out
        return out
    return build


@pytest.fixture
def pipe(verify, signals, make_w1):
    """pipe(**spec) -> (world, b8 = verify_all, sig = compute_all) with the A7 world present."""
    def _run(**spec):
        spec.setdefault("with_a7", True)
        w = make_w1(**spec)
        b8 = verify.verify_all(w.p426, w.rows_root, w.repo)
        sig = signals.compute_all(w.p426, w.rows_root, b8)
        return w, b8, sig
    return _run

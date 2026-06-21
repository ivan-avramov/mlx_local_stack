"""TDD tests for LiveCodeBench grading (release pin, input assembly, parse/degrade)."""
import sys
import types

import bench.benchmarks as B


def test_lcb_release_is_pinned():
    """A concrete release window is pinned (not the moving 'release_latest')."""
    assert isinstance(B.LCB_RELEASE, str)
    assert B.LCB_RELEASE != "release_latest"
    assert B.LCB_RELEASE.startswith("release_")


def test_load_lcb_uses_pinned_release(monkeypatch):
    """_load_lcb passes the pinned release to the dataset loader (not 'release_latest')."""
    captured = {}

    fake_mod = types.ModuleType("lcb_runner.benchmarks.code_generation")

    def fake_loader(release_version=None):
        captured["release"] = release_version
        return []  # empty problem list is fine for this assertion

    fake_mod.load_code_generation_dataset = fake_loader
    monkeypatch.setitem(sys.modules, "lcb_runner", types.ModuleType("lcb_runner"))
    monkeypatch.setitem(sys.modules, "lcb_runner.benchmarks", types.ModuleType("lcb_runner.benchmarks"))
    monkeypatch.setitem(sys.modules, "lcb_runner.benchmarks.code_generation", fake_mod)

    B._load_lcb(limit=None, seed=0)
    assert captured["release"] == B.LCB_RELEASE

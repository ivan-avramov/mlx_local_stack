"""LiveCodeBench grading: dataset config-name drift.

Context, because the failure mode is non-obvious: `livecodebench/code_generation_lite` is a
SCRIPT-BASED dataset and `datasets` >= 5 removed `trust_remote_code` entirely, so it can no longer be
downloaded fresh at any version. Only the local cache remains — and the cache key includes the CONFIG
NAME the caller passed. Today's lcb_runner calls `load_dataset(...)` with no name (=> "default"),
while this box's cache was written by an older lcb_runner as "release_latest". A literal call
therefore fails with "Couldn't find cache ... Available configs: ['release_latest-...']" even though
the correct pinned release IS present (measured 2026-08-15: 880 problems at release_v5).
"""
import pytest

import bench.grade as G


def test_lcb_loader_falls_back_across_config_aliases(monkeypatch):
    """The loader must probe aliases in declared order and report which one resolved."""
    calls = []

    class _FakeProblem:
        def __init__(self, **kw):
            self.kw = kw

    def fake_load_dataset(path, cfg, split=None, version_tag=None):
        calls.append(cfg)
        if cfg == "release_latest":
            raise ValueError("Couldn't find cache")      # simulate a differently-keyed cache
        return [{"a": 1}, {"a": 2}]

    import sys
    import types
    fake_ds = types.ModuleType("datasets")
    fake_ds.load_dataset = fake_load_dataset
    fake_cg = types.ModuleType("lcb_runner.benchmarks.code_generation")
    fake_cg.CodeGenerationProblem = _FakeProblem
    monkeypatch.setitem(sys.modules, "datasets", fake_ds)
    monkeypatch.setitem(sys.modules, "lcb_runner.benchmarks.code_generation", fake_cg)

    problems, cfg = G._load_lcb_problems("release_v5")
    assert calls == ["release_latest", "default"], "aliases must be probed in declared order"
    assert cfg == "default"
    assert len(problems) == 2


def test_lcb_loader_raises_naming_every_alias_when_none_resolve(monkeypatch):
    """A failure must name what was tried — a bare error from inside `datasets` is unactionable."""
    import sys
    import types
    fake_ds = types.ModuleType("datasets")

    def boom(path, cfg, split=None, version_tag=None):
        raise ValueError("nope")

    fake_ds.load_dataset = boom
    fake_cg = types.ModuleType("lcb_runner.benchmarks.code_generation")
    fake_cg.CodeGenerationProblem = object
    monkeypatch.setitem(sys.modules, "datasets", fake_ds)
    monkeypatch.setitem(sys.modules, "lcb_runner.benchmarks.code_generation", fake_cg)

    with pytest.raises(RuntimeError) as ei:
        G._load_lcb_problems("release_v5")
    msg = str(ei.value)
    for cfg in G._LCB_CONFIG_ALIASES:
        assert cfg in msg, f"alias {cfg} missing from the error"
    assert "release_v5" in msg

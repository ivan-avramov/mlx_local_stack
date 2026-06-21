"""TDD tests for LiveCodeBench grading (release pin, input assembly, parse/degrade)."""
import sys
import types

import bench.benchmarks as B
import bench.grade as G


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


def test_lcb_eval_inputs_assembles_and_skips_unknown():
    rows = [
        {"id": "q1", "content": "Here:\n```python\nprint(1)\n```"},
        {"id": "qX", "content": "```python\nprint(9)\n```"},  # unknown id -> skipped
    ]
    sample_by_id = {"q1": '{"inputs": [], "outputs": []}'}
    samples_list, generations_list, ids = G._lcb_eval_inputs(rows, sample_by_id)
    assert ids == ["q1"]
    assert samples_list == [{"input_output": '{"inputs": [], "outputs": []}'}]
    assert len(generations_list) == 1 and len(generations_list[0]) == 1
    assert "print(1)" in generations_list[0][0]  # code extracted from the fenced block


def test_lcb_eval_inputs_empty_when_no_matches():
    rows = [{"id": "qX", "content": "```python\nx=1\n```"}]
    samples_list, generations_list, ids = G._lcb_eval_inputs(rows, {"q1": "IO"})
    assert samples_list == [] and generations_list == [] and ids == []

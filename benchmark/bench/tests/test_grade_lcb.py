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


def test_load_lcb_uses_pinned_release(monkeypatch, tmp_path):
    """On a cache MISS, _load_lcb passes the pinned release to the dataset loader (the
    prompt cache is per-release via its filename, so contamination control is preserved)."""
    captured = {}

    fake_mod = types.ModuleType("lcb_runner.benchmarks.code_generation")

    def fake_loader(release_version=None):
        captured["release"] = release_version
        return []  # empty problem list is fine for this assertion

    fake_mod.load_code_generation_dataset = fake_loader
    monkeypatch.setitem(sys.modules, "lcb_runner", types.ModuleType("lcb_runner"))
    monkeypatch.setitem(sys.modules, "lcb_runner.benchmarks", types.ModuleType("lcb_runner.benchmarks"))
    monkeypatch.setitem(sys.modules, "lcb_runner.benchmarks.code_generation", fake_mod)
    # Force a cache miss so the build path (which calls the loader) runs.
    monkeypatch.setattr(B, "_lcb_prompt_cache_path", lambda: str(tmp_path / "miss.json"))

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


class _FakeProblem:
    def __init__(self, qid, io):
        self.question_id = qid
        self._io = io

    def get_evaluation_sample(self):
        return {"input_output": self._io}


def _install_fake_lcb(monkeypatch, problems, metrics):
    """Inject fake lcb_runner modules so grade_lcb's lazy imports resolve to fakes."""
    base = types.ModuleType("lcb_runner")
    bench_pkg = types.ModuleType("lcb_runner.benchmarks")
    cg = types.ModuleType("lcb_runner.benchmarks.code_generation")
    cg.load_code_generation_dataset = lambda release_version=None: problems
    ev = types.ModuleType("lcb_runner.evaluation")
    ev.codegen_metrics = lambda samples, gens, **kw: [metrics, {}, []]
    for name, mod in [("lcb_runner", base), ("lcb_runner.benchmarks", bench_pkg),
                      ("lcb_runner.benchmarks.code_generation", cg), ("lcb_runner.evaluation", ev)]:
        monkeypatch.setitem(sys.modules, name, mod)


def test_grade_lcb_parses_and_normalizes_percentage(monkeypatch):
    rows = [{"id": "q1", "content": "```python\nprint(1)\n```"},
            {"id": "q2", "content": "```python\nprint(2)\n```"}]
    monkeypatch.setattr(G, "_rows", lambda m, n: rows)
    _install_fake_lcb(monkeypatch,
                      [_FakeProblem("q1", '{"inputs":[],"outputs":[]}'),
                       _FakeProblem("q2", '{"inputs":[],"outputs":[]}')],
                      {"pass@1": 50.0})  # percentage form
    out = G.grade_lcb("livecodebench", "m")
    assert out["n"] == 2 and out["matched"] == 2
    assert out["pass@1"] == 50.0
    assert out["acc"] == 0.5                 # normalized to a fraction
    assert out["release"] == B.LCB_RELEASE


def test_grade_lcb_accepts_fraction_form(monkeypatch):
    monkeypatch.setattr(G, "_rows", lambda m, n: [{"id": "q1", "content": "```python\nx=1\n```"}])
    _install_fake_lcb(monkeypatch, [_FakeProblem("q1", '{"inputs":[],"outputs":[]}')],
                      {"pass@1": 1.0})       # already a fraction (perfect score) -> stays 1.0
    out = G.grade_lcb("livecodebench", "m")
    assert out["acc"] == 1.0


def test_grade_lcb_no_completions(monkeypatch):
    monkeypatch.setattr(G, "_rows", lambda m, n: [])
    out = G.grade_lcb("livecodebench", "m")
    assert out["n"] == 0 and out["acc"] is None
    assert "note" in out


def test_grade_lcb_graceful_degrade_when_lcb_runner_missing(monkeypatch):
    monkeypatch.setattr(G, "_rows", lambda m, n: [{"id": "q1", "content": "```python\nx=1\n```"}])
    monkeypatch.setitem(sys.modules, "lcb_runner", None)  # forces ImportError on `import lcb_runner...`
    out = G.grade_lcb("livecodebench", "m")
    assert out["acc"] is None
    assert "lcb_runner" in out["note"]


def test_grade_lcb_no_rows_match_release(monkeypatch):
    """Completions exist but none match the pinned release's problems -> degrade, not crash."""
    monkeypatch.setattr(G, "_rows", lambda m, n: [{"id": "old-q", "content": "```python\nx=1\n```"}])
    _install_fake_lcb(monkeypatch, [_FakeProblem("q1", "{}")], {"pass@1": 100.0})
    out = G.grade_lcb("livecodebench", "m")
    assert out["n"] == 0 and out["acc"] is None and "match" in out["note"].lower()

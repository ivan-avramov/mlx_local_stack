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
    samples_list, generations_list, ids, orders = G._lcb_eval_inputs(rows, sample_by_id)
    assert ids == ["q1"]
    assert samples_list == [{"input_output": '{"inputs": [], "outputs": []}'}]
    assert len(generations_list) == 1 and len(generations_list[0]) == 1
    assert "print(1)" in generations_list[0][0]  # code extracted from the fenced block
    assert orders == [[0]]                       # a v1 row is sample 0


def test_lcb_eval_inputs_groups_k_samples_under_one_problem():
    """codegen_metrics takes a LIST of completions per problem and reports per-problem pass@1
    over them. Emitting one problem entry per DRAW would report each sample as its own problem —
    silently converting an item-level metric into a draw-level one and breaking the pairing with
    every other grader."""
    rows = [
        {"id": "q1", "sample": 1, "content": "```python\nprint(2)\n```"},
        {"id": "q1", "sample": 0, "content": "```python\nprint(1)\n```"},
        {"id": "q2", "sample": 0, "content": "```python\nprint(3)\n```"},
    ]
    samples_list, generations_list, ids, orders = G._lcb_eval_inputs(
        rows, {"q1": "IO1", "q2": "IO2"})
    assert ids == ["q1", "q2"] and len(samples_list) == 2
    assert orders == [[0, 1], [0]], "samples must be ordered, not left in file order"
    assert "print(1)" in generations_list[0][0] and "print(2)" in generations_list[0][1]


def test_lcb_eval_inputs_empty_when_no_matches():
    rows = [{"id": "qX", "content": "```python\nx=1\n```"}]
    samples_list, generations_list, ids, orders = G._lcb_eval_inputs(rows, {"q1": "IO"})
    assert samples_list == [] and generations_list == [] and ids == [] and orders == []


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


def test_by_difficulty_is_consistent_with_the_aggregate(monkeypatch):
    """INVARIANT: the n-weighted mean of by_difficulty must equal the aggregate acc.

    Live re-grade on M5 (2026-08-11) violated this: three models printed an IDENTICAL breakdown
    (EASY 100% n=3 / MEDIUM 86% n=7 / HARD 60% n=5 -> 12/15 = 80%) while their aggregates were
    93.3 / 93.3 / 86.7. Identical per-difficulty rates across three models with differing
    aggregates is impossible, and the breakdown contradicts the aggregate WITHIN one run — so one
    of the two numbers is wrong, and the per-difficulty split is exactly what the campaign cites
    as its LCB differentiator ("E100/M86/H60").

    This test pins the invariant against FAKE lcb_runner output whose detail and aggregate agree
    by construction. If it passes, our index alignment is sound and the fault is in how the real
    `metrics["detail"]["pass@1"]` is keyed/scaled — which needs one real grading run to settle.
    """
    rows = [{"id": f"q{i}", "sample": 0, "content": "```python\nx=1\n```"} for i in range(4)]
    monkeypatch.setattr(G, "_rows", lambda m, n: rows)
    probs = []
    for i, diff in enumerate(["EASY", "EASY", "MEDIUM", "HARD"]):
        p = _FakeProblem(f"q{i}", '{"inputs":[],"outputs":[]}')
        p.difficulty = diff
        probs.append(p)
    # 3 of 4 pass -> aggregate 75%; detail must say the same, per problem index.
    metrics = {"pass@1": 75.0, "detail": {"pass@1": {0: 1.0, 1: 1.0, 2: 1.0, 3: 0.0}}}
    _install_fake_lcb(monkeypatch, probs, metrics)
    out = G.grade_lcb("livecodebench", "m")

    bd = out["by_difficulty"]
    total_n = sum(v["n"] for v in bd.values())
    weighted = sum(v["n"] * v["pass@1"] for v in bd.values()) / total_n
    assert total_n == 4, f"every graded problem must land in exactly one bucket, got {bd}"
    assert abs(weighted - out["acc"]) < 1e-9, (
        f"by_difficulty ({weighted:.4f}) disagrees with acc ({out['acc']}) — breakdown is "
        f"misaligned with the aggregate: {bd}")
    assert bd["EASY"]["pass@1"] == 1.0 and bd["HARD"]["pass@1"] == 0.0


def test_by_difficulty_survives_string_keyed_detail(monkeypatch):
    """Defensive: json round-trips turn int keys into strings. A str/int mismatch would make every
    lookup miss and silently produce an UNKNOWN-only breakdown."""
    rows = [{"id": f"q{i}", "sample": 0, "content": "```python\nx=1\n```"} for i in range(2)]
    monkeypatch.setattr(G, "_rows", lambda m, n: rows)
    probs = []
    for i, diff in enumerate(["EASY", "HARD"]):
        p = _FakeProblem(f"q{i}", '{"inputs":[],"outputs":[]}')
        p.difficulty = diff
        probs.append(p)
    metrics = {"pass@1": 50.0, "detail": {"pass@1": {"0": 1.0, "1": 0.0}}}
    _install_fake_lcb(monkeypatch, probs, metrics)
    bd = G.grade_lcb("livecodebench", "m")["by_difficulty"]
    assert "UNKNOWN" not in bd, f"string-keyed detail was not handled: {bd}"
    assert bd["EASY"]["pass@1"] == 1.0 and bd["HARD"]["pass@1"] == 0.0


def _install_fake_lcb_with_results(monkeypatch, problems, metrics, results):
    """Like _install_fake_lcb but supplies the RESULTS array too.

    The other fakes pass `results={}`, which sends grade_lcb down its `frac` fallback and so never
    exercises the per-test-verdict path — the path that produced a wrong `acc` in production.
    """
    base = types.ModuleType("lcb_runner")
    bench_pkg = types.ModuleType("lcb_runner.benchmarks")
    cg = types.ModuleType("lcb_runner.benchmarks.code_generation")
    cg.load_code_generation_dataset = lambda release_version=None: problems
    ev = types.ModuleType("lcb_runner.evaluation")
    ev.codegen_metrics = lambda samples, gens, **kw: [metrics, results, []]
    for name, mod in [("lcb_runner", base), ("lcb_runner.benchmarks", bench_pkg),
                      ("lcb_runner.benchmarks.code_generation", cg), ("lcb_runner.evaluation", ev)]:
        monkeypatch.setitem(sys.modules, name, mod)


def _three_problem_setup(monkeypatch, results):
    """3 problems: q0 all-pass, q1 wrong answer, q2 timeout+error. Official pass@1 = 1/3."""
    rows = [{"id": f"q{i}", "sample": 0, "content": "```python\nx=1\n```"} for i in range(3)]
    monkeypatch.setattr(G, "_rows", lambda m, n: rows)
    probs = []
    for i, diff in enumerate(["EASY", "MEDIUM", "HARD"]):
        p = _FakeProblem(f"q{i}", '{"inputs":[],"outputs":[]}')
        p.difficulty = diff
        probs.append(p)
    metrics = {"pass@1": 1 / 3 * 100, "detail": {"pass@1": {0: 1.0, 1: 0.0, 2: 0.0}}}
    _install_fake_lcb_with_results(monkeypatch, probs, metrics, results)
    # Through grade(), NOT grade_lcb(): `_finalize` recomputes `acc` from `items`, and that
    # recomputation is where the sentinel bug actually bites. Calling grade_lcb directly returns
    # its own (correct) acc and cannot observe the fault.
    return G.grade("livecodebench", "m")


def test_lcb_timeout_and_error_sentinels_are_failures_not_passes(monkeypatch):
    """lcb_runner encodes a per-test verdict as 1/True pass, 0/False wrong answer, **-1 timeout**
    and **-2 runtime/compile error** (`evaluation/testing_util.py` appends -2;
    `compute_code_generation_metrics.py` uses `curr_res = [-2]` for a whole-problem error).

    `bool(-1)` and `bool(-2)` are TRUE in Python, so scoring a verdict by truthiness counts every
    timeout and every crash as a PASS. Measured consequence on M5 (2026-08-11): the re-grade
    published LCB `acc` 0.9333 / 0.9333 / 0.8667 for the three candidates while the official
    evaluator's `pass@1` was 0.80 for all three — i.e. a phantom 6.7pp "differentiator" that the
    campaign was sizing future arms against. The by_difficulty breakdown was correct all along.
    """
    out = _three_problem_setup(monkeypatch, {
        0: [[1, 1, 1]],       # all tests pass
        1: [[1, 0, 1]],       # wrong answer on test 2
        2: [[1, -1, -2]],     # timeout then error -> MUST be a failure
    })
    # _finalize rounds to 4dp, so compare at that precision, not float-exact.
    assert out["acc"] == round(1 / 3, 4), (
        f"acc={out['acc']} — a -1/-2 sentinel was scored as a pass; expected {round(1/3,4)}")


def test_lcb_acc_equals_the_official_pass_at_1(monkeypatch):
    """INVARIANT: `acc` is the publishable official number, so it must equal the evaluator's
    `pass@1`. `_finalize` recomputes `acc` from `items`, which is only sound if item `ok` is
    derived exactly as the evaluator derives its verdict. Production violated this silently."""
    out = _three_problem_setup(monkeypatch, {
        0: [[1, 1, 1]], 1: [[1, 0, 1]], 2: [[1, -1, -2]],
    })
    official = out["pass@1"] / 100.0
    assert out["acc"] == round(official, 4), (
        f"acc={out['acc']} != official pass@1={round(official,4)}; the two must not diverge")


def test_lcb_whole_problem_error_scores_zero(monkeypatch):
    """A compile/import failure gives `[-2]` for the whole problem. Truthiness made that a pass."""
    out = _three_problem_setup(monkeypatch, {0: [[1, 1, 1]], 1: [[0]], 2: [[-2]]})
    assert out["acc"] == round(1 / 3, 4), (
        f"acc={out['acc']}; a [-2] problem was scored as a pass")


def test_lcb_graded_fraction_excludes_sentinels(monkeypatch):
    """`acc_graded` is the per-test pass FRACTION; counting -1/-2 as passing inflates it too."""
    out = _three_problem_setup(monkeypatch, {
        0: [[1, 1, 1]],       # 3/3
        1: [[1, 0, 1]],       # 2/3
        2: [[1, -1, -2]],     # 1/3 -- NOT 3/3
    })
    expected = round((1.0 + 2 / 3 + 1 / 3) / 3, 4)
    assert out["acc_graded"] == expected, (
        f"acc_graded={out['acc_graded']} != {expected}; sentinels counted as passing tests")

# LiveCodeBench Grading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the `grade_lcb` stub so LiveCodeBench produces a real, contamination-controlled single-shot coding pass@1 for each model, wired into the existing generate→grade pipeline.

**Architecture:** LiveCodeBench *generation* already works (`benchmarks._load_lcb` loads problems via `lcb_runner`; `generate.run` saves completions to `results/<model>/livecodebench.jsonl`). This plan implements *grading*: pin the LCB release for reproducibility, re-load that release's problems at grade time to recover per-problem test cases, assemble the inputs the official `lcb_runner.evaluation.codegen_metrics` expects, run it (it executes code in its own subprocesses — no bespoke sandbox needed), and parse pass@1. `lcb_runner` is heavy and optional, so it is lazy-imported with graceful degradation, exactly like the existing `grade_evalplus` shells out to `evalplus`.

**Tech Stack:** Python 3 stdlib + the existing harness modules (`benchmarks`, `grade`, `extract`); the official `lcb_runner` package (lazy-imported, installed only where grading runs). pytest for tests, mocking the optional dependency.

## Global Constraints

- **`lcb_runner` is an optional, lazy-imported grade-time dependency.** Never import it at module top. `grade_lcb` must degrade gracefully (return a record with `acc: None` + a `note`) when `lcb_runner` is missing or its dataset/API call fails — never crash the grade batch (matches `grade_evalplus` / `grade.py`'s failure-isolation discipline).
- **Contamination control = pinned release.** Generation and grading MUST use the SAME pinned LiveCodeBench release window; record the release id in the grade output. No `release_latest` (a moving target breaks reproducibility).
- **Grading is mechanical / objective.** No model judge. `codegen_metrics` runs the generated code against the problem's test cases and returns pass@1; that is the correctness oracle. Code is extracted from the saved completion with the existing `extract.extract_code`.
- **Normalize pass@1 to a 0–1 fraction** in the `acc` field (harness convention: `grade_reasoning`/`grade_evalplus` report `acc` as a fraction), while ALSO recording the raw `pass@1` value. lcb_runner may report pass@1 as a percentage; normalize defensively (`>1.0 → ÷100`).
- **`codegen_metrics` API (verified upstream 2026-06-20):** `codegen_metrics(samples_list, generations_list, k_list=[...], num_process_evaluate=16, timeout=6, debug=False) -> [metrics, results, final_metadata]`. `samples_list[i]` is a dict with `"input_output"` = a JSON string (`{"inputs": [...], "outputs": [...], "fn_name"?: ...}`). `generations_list[i]` is a `list[str]` of candidate solutions (we have one completion per problem → `[code]`). `metrics` is a dict with `"pass@1"` etc.
- **Run-time-validated boundary (do not over-test):** the live `lcb_runner` dataset accessor (`problem.get_evaluation_sample()["input_output"]`) and the actual `codegen_metrics` execution are validated on the first real run on a box where `lcb_runner` is installed — the README already states this. Unit tests cover everything that does NOT require the real package (the pure input-assembly + the parse/normalize logic + the graceful-degrade path), mocking `lcb_runner`.
- **Tests run from `benchmark/`:** `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/`.
- **Edit first-party `benchmark/` code only.** No submodule edits.

---

## File Structure

- `benchmark/bench/benchmarks.py` — **Modify.** Add `LCB_RELEASE` constant; `_load_lcb` uses it instead of `"release_latest"`.
- `benchmark/bench/grade.py` — **Modify.** Add pure helper `_lcb_eval_inputs(rows, sample_by_id)`; replace the `grade_lcb` stub with a real implementation (lazy import, re-load pinned release, assemble inputs, run `codegen_metrics`, parse + normalize pass@1, graceful-degrade).
- `benchmark/bench/tests/test_grade_lcb.py` — **Create.** Unit tests for the assembly helper, the parse/normalize integration (mocking `lcb_runner` via `sys.modules`), and graceful degradation.
- `benchmark/README.md` — **Modify.** Update the LiveCodeBench note (currently says grading wiring is pending) — delegate to doc-writer.

No change to `run.py` (its `grade()` dispatch already routes `livecodebench` → `grade_lcb`), `model_params.py`, or `scorecard.py`. No new dependency added to the default test env (`lcb_runner` is install-where-grading-runs, per the existing README note + `requirements.txt`).

---

## Task 1: Pin the LiveCodeBench release

**Files:**
- Modify: `benchmark/bench/benchmarks.py`
- Test: `benchmark/bench/tests/test_grade_lcb.py` (created here; extended in later tasks)

**Interfaces:**
- Consumes: nothing new.
- Produces: `LCB_RELEASE: str` module constant in `benchmarks.py`; `_load_lcb` passes `release_version=LCB_RELEASE` to `load_code_generation_dataset`.

- [ ] **Step 1: Write the failing test**

Create `benchmark/bench/tests/test_grade_lcb.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_grade_lcb.py -v`
Expected: FAIL — `AttributeError: module 'bench.benchmarks' has no attribute 'LCB_RELEASE'`.

- [ ] **Step 3: Implement the pin**

In `benchmark/bench/benchmarks.py`, add the constant near the top (just under the `SPECS` dict is fine):

```python
# Pinned LiveCodeBench release window for contamination control + reproducibility.
# Generation and grading MUST use the same release; the id is recorded in the grade output.
LCB_RELEASE = "release_v5"
```

Then change `_load_lcb` to use it. Replace this line:

```python
    probs = load_code_generation_dataset(release_version="release_latest")
```

with:

```python
    probs = load_code_generation_dataset(release_version=LCB_RELEASE)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_grade_lcb.py -v`
Expected: PASS — both tests.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/benchmarks.py benchmark/bench/tests/test_grade_lcb.py
git commit -m "bench(lcb): pin LiveCodeBench release window for reproducible grading"
```

---

## Task 2: `_lcb_eval_inputs` assembly helper

**Files:**
- Modify: `benchmark/bench/grade.py`
- Test: `benchmark/bench/tests/test_grade_lcb.py`

**Interfaces:**
- Consumes (from grade.py): `extract.extract_code(text) -> str`.
- Produces: `_lcb_eval_inputs(rows: list[dict], sample_by_id: dict) -> tuple[list[dict], list[list[str]], list]` — builds `(samples_list, generations_list, ids)` for `codegen_metrics`: one entry per row whose `id` is present in `sample_by_id`; rows with an unknown id are skipped (so a row that doesn't belong to the pinned release can't crash or mis-score grading).

- [ ] **Step 1: Write the failing test**

Append to `benchmark/bench/tests/test_grade_lcb.py`:

```python
import bench.grade as G


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_grade_lcb.py -v`
Expected: FAIL — `AttributeError: module 'bench.grade' has no attribute '_lcb_eval_inputs'`.

- [ ] **Step 3: Implement the helper**

In `benchmark/bench/grade.py`, add above the existing `grade_lcb`:

```python
def _lcb_eval_inputs(rows, sample_by_id):
    """Build codegen_metrics inputs from saved generation rows + a {question_id: input_output}
    map. One sample per row whose id is in the map (rows from outside the pinned release are
    skipped). Returns (samples_list, generations_list, ids):
      samples_list[i]    = {"input_output": <json str>}
      generations_list[i]= [<extracted code string>]   (one completion per problem)
    """
    samples_list, generations_list, ids = [], [], []
    for r in rows:
        qid = r.get("id")
        io = sample_by_id.get(qid)
        if io is None:
            continue
        code = extract.extract_code(r.get("content", ""))
        samples_list.append({"input_output": io})
        generations_list.append([code])
        ids.append(qid)
    return samples_list, generations_list, ids
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_grade_lcb.py -v`
Expected: PASS — all four tests so far.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/grade.py benchmark/bench/tests/test_grade_lcb.py
git commit -m "bench(lcb): _lcb_eval_inputs assembly helper (codegen_metrics inputs)"
```

---

## Task 3: `grade_lcb` real implementation

**Files:**
- Modify: `benchmark/bench/grade.py`
- Test: `benchmark/bench/tests/test_grade_lcb.py`

**Interfaces:**
- Consumes: `_rows(model, name)` (existing), `_lcb_eval_inputs` (Task 2), `benchmarks.LCB_RELEASE` (Task 1), lazy `lcb_runner.benchmarks.code_generation.load_code_generation_dataset` + `lcb_runner.evaluation.codegen_metrics`.
- Produces: `grade_lcb(name, model) -> dict` with keys `{benchmark, model, n, acc, pass@1, release, matched, total_rows}` on success; `{benchmark, model, n, acc: None, note}` on any degrade path. `acc` is pass@1 normalized to a 0–1 fraction.

- [ ] **Step 1: Write the failing tests**

Append to `benchmark/bench/tests/test_grade_lcb.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_grade_lcb.py -v`
Expected: FAIL — the current stub `grade_lcb` returns `{"acc": None, "note": "lcb grading wiring pending ..."}`, so assertions on `acc`/`pass@1`/`matched` fail.

- [ ] **Step 3: Implement `grade_lcb`**

In `benchmark/bench/grade.py`, replace the entire existing `grade_lcb` function with:

```python
def grade_lcb(name, model):
    """Grade LiveCodeBench via the official lcb_runner executor (lazy, graceful-degrade).
    Re-loads the PINNED release to recover per-problem test cases, runs codegen_metrics
    on the saved completions, and reports pass@1 normalized to a 0-1 fraction."""
    rows = [r for r in _rows(model, name) if not r.get("error")]
    if not rows:
        return {"benchmark": name, "model": model, "n": 0, "acc": None, "note": "no completions"}
    try:
        from lcb_runner.benchmarks.code_generation import load_code_generation_dataset
        from lcb_runner.evaluation import codegen_metrics
    except Exception as e:  # noqa: BLE001 — optional heavy dep
        return {"benchmark": name, "model": model, "n": len(rows), "acc": None,
                "note": f"lcb_runner not available ({type(e).__name__}: {str(e)[:80]}); see benchmark/README.md"}
    try:
        problems = load_code_generation_dataset(release_version=benchmarks.LCB_RELEASE)
        sample_by_id = {getattr(p, "question_id", None): p.get_evaluation_sample()["input_output"]
                        for p in problems}
    except Exception as e:  # noqa: BLE001 — dataset/accessor drift on the installed version
        return {"benchmark": name, "model": model, "n": len(rows), "acc": None,
                "note": f"lcb dataset/sample load failed ({type(e).__name__}: {str(e)[:80]})"}
    samples_list, generations_list, ids = _lcb_eval_inputs(rows, sample_by_id)
    if not samples_list:
        return {"benchmark": name, "model": model, "n": 0, "acc": None,
                "note": f"no saved rows matched the pinned release {benchmarks.LCB_RELEASE}"}
    metrics, _results, _meta = codegen_metrics(samples_list, generations_list,
                                               k_list=[1], num_process_evaluate=8, timeout=6)
    pass1 = metrics.get("pass@1")
    acc = (pass1 / 100.0 if (pass1 is not None and pass1 > 1.0) else pass1)
    return {"benchmark": name, "model": model, "n": len(samples_list), "acc": acc,
            "pass@1": pass1, "release": benchmarks.LCB_RELEASE,
            "matched": len(ids), "total_rows": len(rows)}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_grade_lcb.py -v`
Expected: PASS — all tests (release pin, loader pin, assembly ×2, parse/normalize ×2, no-completions, degrade, no-match).

- [ ] **Step 5: Run the whole suite (no regressions)**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/ -q`
Expected: PASS — full suite green.

- [ ] **Step 6: Commit**

```bash
git add benchmark/bench/grade.py benchmark/bench/tests/test_grade_lcb.py
git commit -m "bench(lcb): wire grade_lcb to codegen_metrics (lazy, graceful-degrade, pass@1)"
```

---

## Task 4: README LiveCodeBench note

**Files:**
- Modify: `benchmark/README.md`

**Interfaces:** none (docs only).

> Delegate to the doc-writer agent. The README currently lists LiveCodeBench grading as "official `lcb_runner`" in the Benchmarks table and the requirements note says wiring is pending — update both to reflect that grading is now wired (lazy/optional dependency, pinned release, install instructions, pass@1 reported as a fraction).

- [ ] **Step 1: Update the LiveCodeBench docs**

In `benchmark/README.md`, ensure the LiveCodeBench install line is present in the Quick-start deps block:

```bash
uv pip install "git+https://github.com/LiveCodeBench/LiveCodeBench.git"   # lcb_runner (grading)
```

And add/adjust a short note near the Benchmarks table:

````markdown
**LiveCodeBench grading** uses the official `lcb_runner` (optional, lazy-imported). Install it
where you run `grade` (`uv pip install "git+https://github.com/LiveCodeBench/LiveCodeBench.git"`);
generation and grading both use the pinned release `benchmarks.LCB_RELEASE` for contamination
control. `grade` reports pass@1 as a 0–1 fraction in `acc` (raw `pass@1` recorded alongside). If
`lcb_runner` is absent, the row degrades to `acc: null` with a note rather than failing the batch.
````

- [ ] **Step 2: Verify the doc claim matches the code**

Confirm `benchmarks.LCB_RELEASE` exists and `grade_lcb` reports `acc` as a fraction:

Run: `cd benchmark && uv run python -c "from bench import benchmarks; print(benchmarks.LCB_RELEASE)"`
Expected: prints the pinned release (e.g. `release_v5`).

- [ ] **Step 3: Commit**

```bash
git add benchmark/README.md
git commit -m "docs(bench): document wired LiveCodeBench grading (lazy dep, pinned release)"
```

---

## Running it (operational — after merge, where lcb_runner is installed)

Not a TDD task. LiveCodeBench is already in the `mid`/`heavy` tiers. To produce real numbers:

```bash
# Install the grader where you run grade (heavy dep; not on the measurement box during a run):
uv pip install "git+https://github.com/LiveCodeBench/LiveCodeBench.git"

# Generate (if not already) then grade — on both candidates:
cd benchmark && uv run python benchmark/run.py generate --tier mid --benches livecodebench --models Qwen3.6-27B-UD-MLX-6bit,gemma-4-26B-A4B-it-QAT-MLX-4bit
uv run python benchmark/run.py grade --tier mid --benches livecodebench
```

First real grade run validates the two run-time boundaries this plan could not unit-test: the live
`problem.get_evaluation_sample()` accessor and the actual `codegen_metrics` execution/scoring
convention (confirm the pass@1 normalization landed right; the defensive `>1.0 → ÷100` handles
either convention).

---

## Self-Review

**Spec coverage** (forward-plan Step-1 "Coding (single-shot): LiveCodeBench"; harness-design §4.4 `livecodebench.py`, §6 "Use LiveCodeBench", §9 contamination control):
- LiveCodeBench grading implemented + execution-gated (codegen_metrics runs tests) → Tasks 2–3. ✓
- Contamination control via pinned release window → Task 1 (`LCB_RELEASE`), recorded in output. ✓
- Lazy/optional dependency + graceful degrade (no batch crash) → Task 3 degrade paths + tests. ✓
- pass@1 reported, normalized to harness `acc` convention → Task 3. ✓
- No bespoke sandbox (lcb_runner self-executes) → recorded as a deliberate scope decision (exec_sandbox deferred to the agentic-coding sub-plan). ✓

**Placeholder scan:** every code step shows full code; every test step shows real assertions + exact command + expected result. The only explicitly run-time-validated items (live lcb accessor + real codegen_metrics execution) are isolated behind graceful-degrade and called out in the Global Constraints + Running-it sections — not left as TODOs. ✓

**Type consistency:** `LCB_RELEASE: str`; `_lcb_eval_inputs(rows, sample_by_id) -> (samples_list, generations_list, ids)` with `samples_list[i] = {"input_output": str}`, `generations_list[i] = [str]`; `grade_lcb(name, model) -> dict`. Used identically across Tasks 1→2→3 and the test file. `grade()`'s existing dispatch (`run.py`/`grade.py`) already calls `grade_lcb(name, model)` — signature unchanged. ✓

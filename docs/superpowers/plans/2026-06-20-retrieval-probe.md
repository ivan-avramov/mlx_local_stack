# Dedicated Retrieval Probe Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated multi-needle retrieval probe that produces a clean accuracy-vs-context **curve** for each model at full production params, replacing the capacity probe's thinking-starved co-signal.

**Architecture:** Extend `bench/retrieval.py` (already has `build_context`/`make_question`/`score`) with seeded per-trial needles, a per-needle `hits()` helper, and a full-curve `run_retrieval_ladder`. Add a thin `bench/run_retrieval.py` CLI that mirrors `run_reasoning.py` (preload → calibrate cpt → production params → ladder → write `results/<model>/retrieval.json`). This is sub-plan #1 of the 5-part Step-1 (agentic-coding) decomposition; it is independently shippable and closes the gemma thinking-starvation cleanup.

**Tech Stack:** Python 3 stdlib only (`random`, `string`, `argparse`, `json`); pytest for tests. No new third-party dependencies. Drives the live `mlx-serve` router over HTTP via the existing `MlxServeDriver`.

## Global Constraints

- **Production params verbatim:** every model call in a quality run uses `bench.model_params.params_for(model)` unchanged (temp/top_p/top_k/min_p/penalties + `enable_thinking` + `thinking_budget` + `max_tokens`). The probe forwards `params` to `driver.complete` and NEVER hardcodes sampling or bounds the thinking budget. `--max-tokens`/`--thinking-budget` CLI flags exist only as explicit operator overrides (default = the model's production value).
- **This is a quality measurement, not a memory measurement.** Unlike the capacity probe (which bounds generation to 256 tokens because the MLX prefill spike is decode-length-independent), the retrieval probe runs full-length production generation so the think trace is never starved.
- **Full curve, not climb-to-cliff.** Retrieval can be non-monotonic; a rung below threshold must NOT stop the ladder. Only a hard failure (every trial at a rung raises — OOM/disconnect at long context) stops it, because larger contexts will also fail. `retrieval_effective_ctx` = the largest L with accuracy ≥ threshold.
- **Match existing harness conventions exactly:** probe module = pure builders/scorers + a ladder fn; CLI = `run_*.py` with `main(argv) -> int`, `calibrate_cpt`, writing `results/<model>/<probe>.json`. Tests use the established `FakeSampler` / scripted-driver / monkeypatched-`main` patterns (see `bench/tests/test_reasoning.py`, `test_run_reasoning.py`).
- **Tests run from `benchmark/`:** `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/`.
- **Edit the parent forks, never `src/*` submodules** — N/A here (this plan touches only `benchmark/`, which is first-party).
- **Backward compatibility:** the existing `test_retrieval.py` tests and `capacity_ladder.py`'s use of `build_context`/`make_question`/`score` must keep passing unchanged.

---

## File Structure

- `benchmark/bench/retrieval.py` — **Modify.** Add `import random`, `import string`, `from .instrument import MemorySampler`; seed-randomized needles in `build_context` (new `seed=0` kwarg, default keeps current behavior deterministic); new `hits()` helper; `RETRIEVAL_GRID`; `run_retrieval_ladder()`. Keep `make_question`/`score`/`DEPTHS`/`FILLER` signatures stable.
- `benchmark/bench/run_retrieval.py` — **Create.** CLI mirroring `run_reasoning.py`; writes `results/<model>/retrieval.json`.
- `benchmark/bench/tests/test_retrieval.py` — **Modify.** Add builder-seed tests, `hits()` tests, and `run_retrieval_ladder` tests (full-curve / no-stop-on-dip / stop-on-hard-error / per-depth / params-forwarded). Keep the 3 existing tests.
- `benchmark/bench/tests/test_run_retrieval.py` — **Create.** CLI tests mirroring `test_run_reasoning.py` (monkeypatched `main`).
- `benchmark/README.md` — **Modify.** Short "Retrieval probe" subsection (delegate to doc-writer).

No change to `scorecard.py`, `requirements.txt`, or `model_params.py`: no new deps, and the dedicated `retrieval.json` is read by the Step-3 synthesis directly (it supersedes the capacity probe's rough `retrieval_acc` co-signal).

---

## Task 1: Seeded multi-needle builder + `hits()`

**Files:**
- Modify: `benchmark/bench/retrieval.py`
- Test: `benchmark/bench/tests/test_retrieval.py`

**Interfaces:**
- Consumes: nothing new (stdlib `random`, `string`).
- Produces:
  - `build_context(target_tokens: int, chars_per_token: float, depths=DEPTHS, seed: int = 0) -> tuple[str, list[str]]` — needles randomized by `seed`, fixed length 8, distinct, returned in ascending-depth order.
  - `hits(response_text: str, needles: list[str]) -> list[bool]` — per-needle substring presence, in needle order.
  - Unchanged: `make_question(needles) -> str`, `score(response_text, needles) -> float`, `DEPTHS`, `FILLER`.

- [ ] **Step 1: Write the failing tests**

Add to `benchmark/bench/tests/test_retrieval.py` (keep the existing 3 tests; extend the import line):

```python
from bench.retrieval import (
    build_context, score, make_question, hits, DEPTHS,
    run_retrieval_ladder, RETRIEVAL_GRID,
)


def test_build_context_seeded_unique_needles():
    _, n0 = build_context(2000, 4.0, seed=0)
    _, n1 = build_context(2000, 4.0, seed=1)
    assert len(set(n0)) == len(n0)          # unique within a context
    assert n0 != n1                          # different seeds -> different needles


def test_build_context_deterministic():
    assert build_context(2000, 4.0, seed=7) == build_context(2000, 4.0, seed=7)


def test_build_context_needles_fixed_length():
    _, needles = build_context(2000, 4.0, seed=3)
    assert all(len(n) == 8 for n in needles)


def test_hits_per_needle():
    _, needles = build_context(2000, 4.0, seed=0)
    assert hits(", ".join(needles), needles) == [True] * len(needles)
    assert hits(needles[2], needles) == [i == 2 for i in range(len(needles))]
    assert hits("", needles) == [False] * len(needles)
    assert hits(None, needles) == [False] * len(needles)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_retrieval.py -v`
Expected: FAIL — `ImportError` on `hits` / `run_retrieval_ladder` / `RETRIEVAL_GRID` (collection error), and the new `build_context(..., seed=...)` tests would fail on the missing `seed` kwarg.

- [ ] **Step 3: Implement the builder + `hits()`**

Replace the top of `benchmark/bench/retrieval.py` (the module docstring through `score`) with:

```python
"""Multi-needle retrieval probe: one unique code per depth, a single query asking
for all of them (multi-key NIAH). Generalizes needle_256k.py so one prefill scores
retrieval across the whole context. Score = fraction of codes returned.

Two consumers:
- capacity_ladder.py uses build_context/make_question/score for the rough memory-probe
  co-signal (bounded generation, thinking-starved by design).
- run_retrieval.py drives the dedicated retrieval CURVE at production params (full
  thinking) via run_retrieval_ladder — the authoritative retrieval-effective-length.
"""
import random
import string

FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "
DEPTHS = (0.1, 0.3, 0.5, 0.7, 0.9)

_NEEDLE_LEN = 8
_ALPHABET = string.ascii_uppercase + string.digits  # never appears in the lowercase filler


def _make_needles(rng: random.Random, n: int) -> list[str]:
    """n distinct fixed-length uppercase/digit tokens. Equal length => none is a
    substring of another; uppercase/digit => never collides with the lowercase filler."""
    needles: list[str] = []
    used: set[str] = set()
    while len(needles) < n:
        cand = "".join(rng.choice(_ALPHABET) for _ in range(_NEEDLE_LEN))
        if cand not in used:
            used.add(cand)
            needles.append(cand)
    return needles


def build_context(target_tokens: int, chars_per_token: float,
                  depths=DEPTHS, seed: int = 0) -> tuple[str, list[str]]:
    """Build a multi-needle context. `seed` randomizes the needle tokens so repeated
    trials at one context length are not degenerate; depths are fixed (the positional
    curve is the measurement). Needles are returned in ascending-depth order and
    inserted deepest-first so earlier inserts don't shift later offsets."""
    rng = random.Random(seed)
    target_chars = int(target_tokens * chars_per_token)
    filler = FILLER * (target_chars // len(FILLER) + 2)
    needles = _make_needles(rng, len(depths))
    chars = list(filler[:target_chars])
    for i in sorted(range(len(depths)), key=lambda k: depths[k], reverse=True):
        pos = min(int(target_chars * depths[i]), len(chars) - 1)
        sentence = f" The secret code number {i} is {needles[i]}. "
        chars[pos:pos] = list(sentence)
    return "".join(chars), needles


def make_question(needles: list[str]) -> str:
    return (f"The document above contains {len(needles)} secret codes, each stated once. "
            f"List all {len(needles)} codes, separated by commas. Output only the codes.")


def hits(response_text: str, needles: list[str]) -> list[bool]:
    """Per-needle presence (substring match), in needle order."""
    text = response_text or ""
    return [n in text for n in needles]


def score(response_text: str, needles: list[str]) -> float:
    if not needles:
        return 0.0
    return sum(hits(response_text, needles)) / len(needles)
```

(The `run_retrieval_ladder` referenced by the new import lands in Task 2; until then the import in the test will still fail — that's expected and resolved at the end of Task 2. To keep Task 1 self-contained and green, temporarily import only `hits` and the builder in Step 1's test, OR proceed knowing the ladder tests are added in Task 2. For a clean per-task gate, in Step 1 import only the names this task defines:)

Use this import line for Task 1's test edit instead, and widen it in Task 2:

```python
from bench.retrieval import build_context, score, make_question, hits, DEPTHS
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_retrieval.py -v`
Expected: PASS — all existing tests (`test_build_places_all_needles_in_order`, `test_score_is_fraction_found`, `test_question_mentions_count`) plus the 4 new builder/`hits` tests. The order-and-uniqueness invariants the old tests assert still hold because needles remain fixed-length-8, distinct, and inserted deepest-first.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/retrieval.py benchmark/bench/tests/test_retrieval.py
git commit -m "bench(retrieval): seeded per-trial needles + per-needle hits()"
```

---

## Task 2: `run_retrieval_ladder` full-curve ladder

**Files:**
- Modify: `benchmark/bench/retrieval.py`
- Test: `benchmark/bench/tests/test_retrieval.py`

**Interfaces:**
- Consumes (from Task 1): `build_context`, `make_question`, `hits`, `DEPTHS`; `MemorySampler` (imported at module top).
- Produces:
  - `RETRIEVAL_GRID = (8000, 32000, 64000, 128000, 192000, 256000)`
  - `run_retrieval_ladder(driver, model, chars_per_token, model_pid, params, grid=RETRIEVAL_GRID, threshold=0.85, samples=5, depths=DEPTHS, sampler_factory=MemorySampler) -> list[dict]`
  - Each record: `{"ctx": int, "accuracy": float, "per_depth_acc": list[float], "samples": int, "needles": int, "errors": int}`.

- [ ] **Step 1: Write the failing tests**

Widen the import line at the top of `benchmark/bench/tests/test_retrieval.py` to include the ladder, and append the ladder tests + scripted drivers:

```python
from bench.retrieval import (
    build_context, score, make_question, hits, DEPTHS,
    run_retrieval_ladder, RETRIEVAL_GRID,
)
import re


class FakeSampler:
    def __init__(self, pid=None, interval=0.2):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    system_peak_gb = 30.0
    peak_rss_gb = 20.0


_NEEDLE_RE = re.compile(r"is ([A-Z0-9]{8})\.")
_PROD = {"max_tokens": 256, "temperature": 0.7, "thinking_budget": 128,
         "top_p": 0.95, "enable_thinking": True}


def _ok(content):
    return {"content": content, "prompt_tokens": 100, "decode_tps": 50.0,
            "peak_mem_gb": 20.0, "prefill_s": 0.5, "prefill_tps": 200, "wall_s": 1.0}


class AllNeedlesDriver:
    """Echoes every needle present in the prompt -> accuracy 1.0."""
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return _ok(", ".join(_NEEDLE_RE.findall(messages[-1]["content"])))


class NoNeedlesDriver:
    """Returns no codes -> accuracy 0.0, but does NOT raise."""
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return _ok("I could not find any codes.")


class ExplodingDriver:
    """Raises on every call -> simulates a hard OOM at this context length."""
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        raise RuntimeError("server exploded (OOM)")


def test_ladder_full_curve_all_correct():
    recs = run_retrieval_ladder(AllNeedlesDriver(), "m", 4.0, model_pid=1,
                                params=_PROD, grid=(8000, 16000, 24000), samples=3,
                                sampler_factory=FakeSampler)
    assert len(recs) == 3
    assert all(r["accuracy"] == 1.0 for r in recs)
    assert all(len(r["per_depth_acc"]) == len(DEPTHS) for r in recs)


def test_ladder_does_not_stop_on_low_accuracy():
    """KEY DIFFERENCE FROM REASONING: a rung below threshold (no hard error) does not
    stop the full curve."""
    recs = run_retrieval_ladder(NoNeedlesDriver(), "m", 4.0, model_pid=1,
                                params=_PROD, grid=(8000, 16000, 24000),
                                threshold=0.85, samples=3, sampler_factory=FakeSampler)
    assert len(recs) == 3                         # all rungs ran despite acc=0
    assert all(r["accuracy"] == 0.0 for r in recs)
    assert all(r["errors"] == 0 for r in recs)


def test_ladder_stops_on_hard_error():
    """Every trial at a rung raising (errors == samples ~ OOM) stops the ladder."""
    recs = run_retrieval_ladder(ExplodingDriver(), "m", 4.0, model_pid=1,
                                params=_PROD, grid=(8000, 16000, 24000), samples=2,
                                sampler_factory=FakeSampler)
    assert len(recs) == 1
    assert recs[0]["errors"] == 2
    assert recs[0]["accuracy"] == 0.0


def test_ladder_per_depth_breakdown():
    recs = run_retrieval_ladder(AllNeedlesDriver(), "m", 4.0, model_pid=1,
                                params=_PROD, grid=(8000,), samples=2,
                                sampler_factory=FakeSampler)
    assert recs[0]["per_depth_acc"] == [1.0, 1.0, 1.0, 1.0, 1.0]


def test_ladder_params_forwarded():
    received = []

    class RecordParamsDriver:
        def complete(self, model, messages, params, timeout=3600):
            received.append(dict(params))
            return _ok(", ".join(_NEEDLE_RE.findall(messages[-1]["content"])))

    custom = {"max_tokens": 512, "temperature": 0.7, "thinking_budget": 999,
              "top_p": 0.95, "enable_thinking": True}
    run_retrieval_ladder(RecordParamsDriver(), "m", 4.0, model_pid=1, params=custom,
                         grid=(8000,), samples=1, sampler_factory=FakeSampler)
    assert received[0]["thinking_budget"] == 999    # not bounded/overridden
    assert received[0]["temperature"] == 0.7
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_retrieval.py -v`
Expected: FAIL — `ImportError`/`AttributeError` on `run_retrieval_ladder` and `RETRIEVAL_GRID`.

- [ ] **Step 3: Implement the ladder**

First add the instrument import to the top of `benchmark/bench/retrieval.py`, immediately under `import string`:

```python
from .instrument import MemorySampler
```

Then append to the end of the file (after `score`) — `RETRIEVAL_GRID` is defined here, before the function that uses it as a default arg:

```python
RETRIEVAL_GRID = (8000, 32000, 64000, 128000, 192000, 256000)


def run_retrieval_ladder(driver, model, chars_per_token, model_pid, params,
                         grid=RETRIEVAL_GRID, threshold: float = 0.85, samples: int = 5,
                         depths=DEPTHS, sampler_factory=MemorySampler) -> list[dict]:
    """FULL CURVE (not climb-to-cliff): run multi-needle retrieval at every context
    length in `grid`. Retrieval can be non-monotonic (a model may dip mid-context and
    recover), so — unlike run_reasoning_ladder — a rung below threshold does NOT stop
    the ladder. Only a HARD failure (every trial at a rung raises => errors == samples,
    which at long context means OOM/disconnect) stops it, because larger contexts will
    also fail.

    For each rung, runs `samples` trials with distinct needle seeds (seed = ctx*1000 +
    trial). `params` is forwarded verbatim to driver.complete — this is a quality
    measurement, so full production params (incl. thinking_budget) are used unbounded.

    Returns per-rung dicts: {"ctx", "accuracy", "per_depth_acc", "samples", "needles",
    "errors"} where accuracy is the mean fraction of needles returned across trials and
    per_depth_acc[d] is the hit rate at depth d across trials.
    """
    records: list[dict] = []
    n_dep = len(depths)
    for ctx_len in grid:
        trial_hits: list[list[bool]] = []
        errors = 0
        for trial in range(samples):
            seed = ctx_len * 1000 + trial
            context, needles = build_context(ctx_len, chars_per_token,
                                             depths=depths, seed=seed)
            messages = [{"role": "user",
                         "content": context + "\n\n" + make_question(needles)}]
            with sampler_factory(pid=model_pid):
                try:
                    result = driver.complete(model, messages, params)
                    trial_hits.append(hits(result.get("content", ""), needles))
                except Exception:  # noqa: BLE001 — OOM/disconnect at this ctx
                    trial_hits.append([False] * n_dep)
                    errors += 1
        accuracy = sum(sum(h) / n_dep for h in trial_hits) / len(trial_hits)
        per_depth_acc = [round(sum(h[d] for h in trial_hits) / len(trial_hits), 3)
                         for d in range(n_dep)]
        records.append({"ctx": ctx_len, "accuracy": round(accuracy, 3),
                        "per_depth_acc": per_depth_acc, "samples": samples,
                        "needles": n_dep, "errors": errors})
        if errors == samples:  # hard failure (OOM) at this ctx; larger will also fail
            break
    return records
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_retrieval.py -v`
Expected: PASS — all builder, `hits`, and 5 ladder tests.

- [ ] **Step 5: Run the full suite to confirm no regressions (capacity_ladder still imports retrieval cleanly)**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/ -q`
Expected: PASS — entire suite, including `test_capacity_ladder.py` (which imports `build_context`/`make_question`/`score`).

- [ ] **Step 6: Commit**

```bash
git add benchmark/bench/retrieval.py benchmark/bench/tests/test_retrieval.py
git commit -m "bench(retrieval): full-curve run_retrieval_ladder with per-depth breakdown"
```

---

## Task 3: `run_retrieval.py` CLI

**Files:**
- Create: `benchmark/bench/run_retrieval.py`
- Test: `benchmark/bench/tests/test_run_retrieval.py`

**Interfaces:**
- Consumes (from Task 2): `run_retrieval_ladder`, `RETRIEVAL_GRID`, `DEPTHS`; `MlxServeDriver`; `MemorySampler`, `system_used_gb`, `find_model_server_pid`; `params_for`.
- Produces:
  - `calibrate_cpt(driver, model: str) -> float`
  - `main(argv=None) -> int` — writes `results/<model>/retrieval.json` =
    `{"model", "axis": "retrieval", "task": "multi_needle_niah", "threshold", "grid", "depths", "records", "retrieval_effective_ctx"}` where `retrieval_effective_ctx = max(ctx for ctx with accuracy >= threshold)` or `None`.
  - Module-level patch targets (for tests, mirroring `run_reasoning.py`): `MlxServeDriver`, `MemorySampler`, `system_used_gb`, `find_model_server_pid`, `run_retrieval_ladder`, `RESULTS`.

- [ ] **Step 1: Write the failing tests**

Create `benchmark/bench/tests/test_run_retrieval.py`:

```python
"""TDD tests for bench.run_retrieval CLI."""
import json
import os

import bench.run_retrieval as R
from bench.model_params import params_for


class FakeDriver:
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return {"content": "ABCD1234", "prompt_tokens": 100, "prefill_s": 0.5,
                "prefill_tps": 200, "decode_tps": 50.0, "peak_mem_gb": 20.0, "wall_s": 1.0}


class FakeSampler:
    def __init__(self, pid=None, interval=0.2):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    system_peak_gb = 30.0
    peak_rss_gb = 20.0


CANNED_PASS_FAIL = [
    {"ctx": 8000, "accuracy": 1.0, "per_depth_acc": [1, 1, 1, 1, 1], "samples": 5, "needles": 5, "errors": 0},
    {"ctx": 32000, "accuracy": 0.4, "per_depth_acc": [1, 1, 0, 0, 0], "samples": 5, "needles": 5, "errors": 0},
]
CANNED_DIP_RECOVER = [
    {"ctx": 8000, "accuracy": 1.0, "per_depth_acc": [1, 1, 1, 1, 1], "samples": 5, "needles": 5, "errors": 0},
    {"ctx": 32000, "accuracy": 0.4, "per_depth_acc": [1, 1, 0, 0, 0], "samples": 5, "needles": 5, "errors": 0},
    {"ctx": 64000, "accuracy": 0.9, "per_depth_acc": [1, 1, 1, 1, 0.5], "samples": 5, "needles": 5, "errors": 0},
]
CANNED_ALL_FAIL = [
    {"ctx": 8000, "accuracy": 0.2, "per_depth_acc": [1, 0, 0, 0, 0], "samples": 5, "needles": 5, "errors": 0},
]


def _run_main(monkeypatch, tmp_path, canned, extra_argv=None):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_retrieval_ladder", lambda *a, **kw: canned)
    argv = ["--model", "mymodel", "--grid", "8000,32000", "--no-preload"]
    if extra_argv:
        argv += extra_argv
    return R.main(argv)


def test_main_returns_0(monkeypatch, tmp_path):
    assert _run_main(monkeypatch, tmp_path, CANNED_PASS_FAIL) == 0


def test_main_writes_retrieval_json(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_PASS_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "retrieval.json")))
    assert out["model"] == "mymodel"
    assert out["axis"] == "retrieval"
    assert out["task"] == "multi_needle_niah"
    assert len(out["records"]) == 2


def test_effective_ctx_largest_passing(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_PASS_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "retrieval.json")))
    assert out["retrieval_effective_ctx"] == 8000


def test_effective_ctx_dip_then_recover(monkeypatch, tmp_path):
    """Full curve: a mid-context dip does not cap the effective length; the largest
    passing rung wins (distinguishes retrieval from the reasoning climb-to-cliff)."""
    _run_main(monkeypatch, tmp_path, CANNED_DIP_RECOVER)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "retrieval.json")))
    assert out["retrieval_effective_ctx"] == 64000


def test_effective_ctx_none_when_all_fail(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_ALL_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "retrieval.json")))
    assert out["retrieval_effective_ctx"] is None


def test_json_has_grid_threshold_depths(monkeypatch, tmp_path):
    _run_main(monkeypatch, tmp_path, CANNED_PASS_FAIL)
    out = json.load(open(os.path.join(tmp_path, "mymodel", "retrieval.json")))
    assert "grid" in out and "threshold" in out and "depths" in out
    assert out["depths"] == [0.1, 0.3, 0.5, 0.7, 0.9]


def test_calibrate_cpt_positive():
    assert R.calibrate_cpt(FakeDriver(), "m") > 0


def test_params_via_params_for(monkeypatch, tmp_path):
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params")
        return CANNED_PASS_FAIL

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_retrieval_ladder", fake_ladder)
    R.main(["--model", "Qwen3.6-27B-UD-MLX-6bit", "--grid", "8000,32000", "--no-preload"])
    expected = params_for("Qwen3.6-27B-UD-MLX-6bit")
    assert captured["params"]["thinking_budget"] == expected["thinking_budget"]
    assert captured["params"]["max_tokens"] == expected["max_tokens"]


def test_thinking_budget_override(monkeypatch, tmp_path):
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params")
        return CANNED_PASS_FAIL

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_retrieval_ladder", fake_ladder)
    R.main(["--model", "Qwen3.6-27B-UD-MLX-6bit", "--grid", "8000", "--no-preload",
            "--thinking-budget", "4096"])
    assert captured["params"]["thinking_budget"] == 4096
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_run_retrieval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bench.run_retrieval'`.

- [ ] **Step 3: Implement the CLI**

Create `benchmark/bench/run_retrieval.py`:

```python
"""CLI: run the dedicated retrieval ladder (multi-needle NIAH) for one model on the box
under test, at PRODUCTION params (full thinking budget — the clean retrieval curve, not
the capacity probe's bounded co-signal).

  cd benchmark && uv run python -m bench.run_retrieval --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/retrieval.json."""
import argparse
import json
import os
import time

from .driver import MlxServeDriver
from .instrument import MemorySampler, system_used_gb, find_model_server_pid
from .model_params import params_for
from .retrieval import run_retrieval_ladder, RETRIEVAL_GRID, DEPTHS

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")

_CAL_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "


def calibrate_cpt(driver, model: str) -> float:
    out = driver.complete(model, [{"role": "user", "content": _CAL_FILLER * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    chars = len(_CAL_FILLER * 200)
    pt = out.get("prompt_tokens") or 1
    return chars / pt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Retrieval ladder (multi-needle NIAH curve at production params).")
    ap.add_argument("--model", required=True)
    ap.add_argument("--grid", default=",".join(str(g) for g in RETRIEVAL_GRID))
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Override production max_tokens (default: model's production value)")
    ap.add_argument("--thinking-budget", type=int, default=None,
                    help="Override production thinking_budget (default: model's production value)")
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)

    grid = tuple(int(x) for x in args.grid.split(","))

    driver = MlxServeDriver()
    if not args.no_preload:
        driver.preload(args.model)

    # Find the model server subprocess (best-effort; retrieval doesn't gate on memory).
    model_pid = None
    for _ in range(10):
        model_pid = find_model_server_pid()
        if model_pid is not None:
            break
        time.sleep(1)
    if model_pid is None:
        print("[retrieval] WARNING: model server process not found; "
              "memory sampling disabled", flush=True)

    cpt = calibrate_cpt(driver, args.model)

    # Production params verbatim; apply explicit CLI overrides only.
    params = params_for(args.model)
    if args.max_tokens is not None:
        params["max_tokens"] = args.max_tokens
    if args.thinking_budget is not None:
        params["thinking_budget"] = args.thinking_budget

    print(f"[retrieval] {args.model} cpt={cpt:.2f} grid={grid} "
          f"threshold={args.threshold} samples={args.samples}", flush=True)
    print(f"[retrieval] params: temp={params.get('temperature')} "
          f"top_p={params.get('top_p')} "
          f"thinking_budget={params.get('thinking_budget')} "
          f"max_tokens={params.get('max_tokens')}", flush=True)

    records = run_retrieval_ladder(
        driver, args.model, cpt, model_pid=model_pid, params=params,
        grid=grid, threshold=args.threshold, samples=args.samples,
        sampler_factory=MemorySampler)

    for r in records:
        print(f"[retrieval] ctx={r['ctx']} acc={r['accuracy']} "
              f"per_depth={r['per_depth_acc']} errors={r['errors']}", flush=True)

    passing = [r["ctx"] for r in records if r["accuracy"] >= args.threshold]
    retrieval_effective_ctx = max(passing) if passing else None

    result = {
        "model": args.model,
        "axis": "retrieval",
        "task": "multi_needle_niah",
        "threshold": args.threshold,
        "grid": list(grid),
        "depths": list(DEPTHS),
        "records": records,
        "retrieval_effective_ctx": retrieval_effective_ctx,
    }

    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "retrieval.json"), "w") as f:
        json.dump(result, f, indent=2)

    print(f"[retrieval] RETRIEVAL_EFFECTIVE_CTX={retrieval_effective_ctx}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_run_retrieval.py -v`
Expected: PASS — all 9 CLI tests.

- [ ] **Step 5: Run the whole suite**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/ -q`
Expected: PASS — entire suite green.

- [ ] **Step 6: Commit**

```bash
git add benchmark/bench/run_retrieval.py benchmark/bench/tests/test_run_retrieval.py
git commit -m "bench(retrieval): run_retrieval.py CLI -> results/<model>/retrieval.json"
```

---

## Task 4: README "Retrieval probe" subsection

**Files:**
- Modify: `benchmark/README.md`

**Interfaces:** none (docs only).

> Per the project's global instruction, **delegate this task to the doc-writer agent.** Brief: add a short subsection documenting the dedicated retrieval probe — what it measures (multi-needle NIAH accuracy-vs-context curve at production params, distinct from the capacity probe's thinking-starved co-signal), the run command, the output file, and that it is a full curve (non-monotonic; `retrieval_effective_ctx` = largest L ≥ threshold).

- [ ] **Step 1: Add the subsection**

Add to `benchmark/README.md` after the "Benchmarks" table (verbatim content for the doc-writer to place):

````markdown
## Retrieval probe (dedicated)

`bench/run_retrieval.py` measures multi-needle NIAH retrieval as a clean
accuracy-vs-context **curve** at full production params — distinct from the capacity
probe, whose retrieval number is a thinking-starved co-signal (256-token answer budget).
Five distinct codes are planted at depths {0.1,0.3,0.5,0.7,0.9}; the model is asked to
list all of them; accuracy = fraction returned, with a per-depth breakdown.

```bash
cd benchmark && uv run python -m bench.run_retrieval --model Qwen3.6-27B-UD-MLX-6bit
```

Writes `results/<model>/retrieval.json` with per-rung `accuracy` + `per_depth_acc` and a
headline `retrieval_effective_ctx` (largest context length with accuracy ≥ 0.85). It is a
**full curve**, not climb-to-cliff: a mid-context dip does not stop the ladder (retrieval
can recover); only a hard OOM at a context length stops it. Run Qwen's 192K/256K rungs on
the M5 (browser-closed/clean) profile.
````

- [ ] **Step 2: Verify the doc renders and the command matches the CLI**

Run: `cd benchmark && uv run python -m bench.run_retrieval --help`
Expected: usage shows `--model`, `--grid`, `--samples`, `--threshold`, `--max-tokens`, `--thinking-budget`, `--no-preload`.

- [ ] **Step 3: Commit**

```bash
git add benchmark/README.md
git commit -m "docs(bench): document the dedicated retrieval probe"
```

---

## Running it (operational — after merge, on the measurement box)

Not a TDD task; run against the live stack on a quiet box, one model at a time.

```bash
# Lean router (no OWUI/docker):
MLX_SERVE_CONFIG=main_models.yaml uv run mlx-serve start    # local M2
# On M5: PATH=/opt/homebrew/bin:$PATH; set -a; . ./.env; set +a; then the same start.

# gemma daily-driver (local M2 is fine to 256K — 40.5GB peak):
cd benchmark && uv run python -m bench.run_retrieval --model gemma-4-26B-A4B-it-QAT-MLX-4bit

# Qwen reasoner: 192K fits 46GB; run 256K on the M5 (clean) profile:
cd benchmark && uv run python -m bench.run_retrieval --model Qwen3.6-27B-UD-MLX-6bit
```

This closes the gemma thinking-starvation cleanup and produces the authoritative
`retrieval_effective_ctx` for both candidates, feeding the Step-3 scorecard.

---

## Self-Review

**Spec coverage** (against forward-plan Step-1 item #2 + harness-design §4.4 `ruler.py`/retrieval, §7 grids):
- "Dedicated retrieval probe (multi-needle/NIAH) at production params → clean retrieval curve for both models" → Tasks 1–3 (`run_retrieval_ladder` + CLI, `params_for` verbatim, full thinking). ✓
- "Closes the gemma thinking-starvation cleanup" → full-thinking generation (no 256-token cap); operational note runs gemma + Qwen. ✓
- §7 effective-length threshold 0.85, per-(L) accuracy, multiple depths → `threshold=0.85`, `per_depth_acc`. ✓
- §2 retrieval reported as accuracy-vs-L curve, never conflated with reasoning → separate `retrieval.json`, full curve, `axis="retrieval"`. ✓
- Memory not re-gated (capacity already did) → ladder stops only on hard OOM, no GB gate. ✓

**Placeholder scan:** no TBD/TODO/"add error handling"/"similar to Task N"; every code step shows full code; every test step shows real assertions and the exact run command + expected result. ✓

**Type consistency:** `build_context(..., seed=0)`, `hits(text, needles) -> list[bool]`, `run_retrieval_ladder(...) -> list[dict]` with fields `{ctx, accuracy, per_depth_acc, samples, needles, errors}`, and `main`'s `retrieval.json` schema are used identically across Tasks 1→2→3 and both test files. CLI patch targets (`MlxServeDriver`, `MemorySampler`, `system_used_gb`, `find_model_server_pid`, `run_retrieval_ladder`, `RESULTS`) are all module-level imports in `run_retrieval.py`, matching the monkeypatch calls in `test_run_retrieval.py`. ✓

**Note on Task 1 import staging:** Task 1's test edit imports only names Task 1 defines (`build_context, score, make_question, hits, DEPTHS`); Task 2 widens the import to add `run_retrieval_ladder, RETRIEVAL_GRID`. This keeps each task's test gate green on its own.

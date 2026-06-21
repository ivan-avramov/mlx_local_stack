# Heavy-Reasoning Probes (Aggregation + Latent) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase-1 Step-2 "honest reasoning ceiling" tooling — a RULER-style **aggregation** probe (common-words extraction) and a NoLiMa-style **latent** reasoning probe — as self-contained, synthetic, exact-match probes that climb-to-cliff and auto-extend past 64K until each model fails.

**Architecture:** Two new probes that mirror the existing `bench/reasoning.py` + `bench/run_reasoning.py` pattern exactly: a pure module (synthetic context generator + exact-match scorer + a climb-to-cliff ladder) and a thin `run_*.py` CLI (preload → calibrate cpt → production params → ladder → write `results/<model>/<probe>.json`). No external datasets, packages, or network — fully synthetic and deterministic by seed, so they build and unit-test with zero heavy deps and run on the live stack with the same `MlxServeDriver` the other probes use.

**Tech Stack:** Python 3 stdlib (`random`, `re`); the existing `bench` driver/instrument/model_params; pytest. No new dependencies.

## Global Constraints

- **Self-contained + synthetic.** Both probes generate their own contexts deterministically from a seed (like `reasoning.py`'s `build_vartrack`). No external dataset, no network, no license entanglement.
- **NoLiMa-STYLE, not the official dataset (deliberate, documented).** The official NoLiMa dataset (`amodaresi/NoLiMa`) is under the restrictive Adobe Research License; for transferable, self-contained tooling and our *relative* (Qwen-vs-gemma) comparison goal, the latent probe uses a self-authored curated set of lexically-disjoint, 1-hop world-knowledge associations (the property NoLiMa isolates: answer requires latent inference, not lexical match). This measures relative latent-reasoning depth, NOT official-leaderboard parity. Swapping in the official dataset is a documented future option if absolute parity is wanted.
- **Production params verbatim.** Every model call uses `model_params.params_for(model)` unchanged (full thinking_budget); `--max-tokens`/`--thinking-budget` are operator overrides only. These are quality measurements.
- **Climb-to-cliff + auto-extend.** Run the base grid `{8K,16K,24K,32K,48K,64K}`; stop at the first rung below threshold (the cliff). If the top planned rung still passes, AUTO-EXTEND in `+8K` steps until a rung fails or `max_ctx` is reached (the forward plan's "extend past 64K in 8K steps until each model cliffs"). Report the cliff per probe; `effective_ctx` = largest passing rung.
- **Exact-match scoring, no judge.** Aggregation = fraction of the K target words returned; latent = the correct character name returned. Deterministic, in-process.
- **Mirror the existing probe conventions exactly:** module = generator + scorer + ladder fn; CLI = `run_*.py` with `main(argv)->int`, `calibrate_cpt`, writing `results/<model>/<probe>.json`. Tests use the established `FakeSampler` / scripted-driver / monkeypatched-`main` patterns (see `bench/tests/test_reasoning.py` / `test_run_reasoning.py`).
- **Tests run from `benchmark/`:** `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/`.

---

## File Structure

- `benchmark/bench/aggregation.py` — **Create.** `AGG_GRID`; `build_cwe(target_tokens, cpt, k, freq_common, freq_uncommon, seed) -> (context, targets, question)`; `score_cwe(response, targets) -> float`; `run_aggregation_ladder(...) -> list[dict]` (climb-to-cliff + auto-extend).
- `benchmark/bench/run_aggregation.py` — **Create.** CLI → `results/<model>/aggregation.json`.
- `benchmark/bench/latent.py` — **Create.** `LATENT_GRID`; `ASSOCIATIONS` (curated needle/question pairs); `NAMES`; `build_latent(target_tokens, cpt, seed) -> (context, answer_name, question)`; `score_latent(response, answer_name) -> float`; `run_latent_ladder(...) -> list[dict]`.
- `benchmark/bench/run_latent.py` — **Create.** CLI → `results/<model>/latent.json`.
- `benchmark/bench/tests/test_aggregation.py`, `benchmark/bench/tests/test_latent.py` — **Create.**
- `benchmark/README.md` — **Modify.** Heavy-reasoning section (doc-writer).

No change to `run.py`/`benchmarks.py`/`grade.py`/`scorecard.py` (standalone probes, like `reasoning.py`).

---

## Task 1: Aggregation probe module (`aggregation.py`)

**Files:**
- Create: `benchmark/bench/aggregation.py`
- Test: `benchmark/bench/tests/test_aggregation.py`

**Interfaces:**
- Consumes: `MemorySampler` from `.instrument`.
- Produces:
  - `AGG_GRID = (8000, 16000, 24000, 32000, 48000, 64000)`
  - `build_cwe(target_tokens, chars_per_token, k=5, freq_common=30, freq_uncommon=3, seed=0) -> (str, list[str], str)` — a shuffled word stream where `k` target words each appear `freq_common` times and distractor words each appear `freq_uncommon` times, filling ~`target_tokens`; returns `(context, targets, question)`.
  - `score_cwe(response, targets) -> float` — fraction of target words present (whole-word, case-insensitive).
  - `run_aggregation_ladder(driver, model, chars_per_token, model_pid, params, grid=AGG_GRID, threshold=0.85, samples=5, k=5, freq_common=30, freq_uncommon=3, extend_step=8000, max_ctx=131072, sampler_factory=MemorySampler) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

Create `benchmark/bench/tests/test_aggregation.py`:

```python
"""TDD tests for bench.aggregation — RULER-style common-words extraction probe."""
import re

import bench.aggregation as AG


def test_build_cwe_targets_are_most_frequent():
    ctx, targets, q = AG.build_cwe(4000, chars_per_token=4.0, k=5, freq_common=30,
                                   freq_uncommon=3, seed=1)
    assert len(targets) == 5 and len(set(targets)) == 5
    counts = {t: len(re.findall(rf"\b{re.escape(t)}\b", ctx)) for t in targets}
    # every target appears freq_common times
    assert all(c == 30 for c in counts.values()), counts
    # question mentions how many words to return
    assert "5" in q


def test_build_cwe_deterministic():
    assert AG.build_cwe(3000, 4.0, seed=7) == AG.build_cwe(3000, 4.0, seed=7)


def test_build_cwe_targets_beat_distractors():
    ctx, targets, _ = AG.build_cwe(6000, 4.0, k=3, freq_common=40, freq_uncommon=2, seed=3)
    words = re.findall(r"\b[a-z]+\b", ctx)
    from collections import Counter
    freq = Counter(words)
    top3 = {w for w, _ in freq.most_common(3)}
    assert set(targets) == top3      # the targets are exactly the 3 most frequent


def test_score_cwe_fraction():
    targets = ["alpha", "bravo", "charlie", "delta", "echo"]
    assert AG.score_cwe("alpha, bravo, charlie, delta, echo", targets) == 1.0
    assert AG.score_cwe("ALPHA and BRAVO only", targets) == 2 / 5
    assert AG.score_cwe("none here", targets) == 0.0


def test_score_cwe_whole_word_only():
    # 'alpha' should not match inside 'alphabet'
    assert AG.score_cwe("alphabet soup", ["alpha"]) == 0.0


class _FakeSampler:
    def __init__(self, pid=None, interval=0.2):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _OKDriver:
    def complete(self, model, messages, params, timeout=3600):
        return {"content": "x", "prompt_tokens": 100, "decode_tps": 1.0, "peak_mem_gb": 1.0,
                "prefill_s": 0.1, "prefill_tps": 1, "wall_s": 0.1}


def test_aggregation_ladder_stops_at_cliff(monkeypatch):
    """Climb-to-cliff: a rung below threshold stops the ladder. The scorer is stubbed by a
    call counter (samples=2): the first rung passes, the second fails."""
    calls = {"n": 0}

    def stub(resp, targets):
        calls["n"] += 1
        return 1.0 if calls["n"] <= 2 else 0.0

    monkeypatch.setattr(AG, "score_cwe", stub)
    recs = AG.run_aggregation_ladder(_OKDriver(), "m", 4.0, model_pid=1, params={},
                                     grid=(1000, 2000, 3000), threshold=0.85, samples=2,
                                     sampler_factory=_FakeSampler)
    assert [r["ctx"] for r in recs] == [1000, 2000]      # stopped at the cliff (rung2 never run)
    assert recs[0]["accuracy"] == 1.0 and recs[1]["accuracy"] == 0.0


def test_aggregation_ladder_auto_extends_past_grid(monkeypatch):
    """If the top planned rung still passes, the ladder extends in +extend_step steps up to
    max_ctx, then stops."""
    monkeypatch.setattr(AG, "score_cwe", lambda resp, targets: 1.0)   # always pass
    recs = AG.run_aggregation_ladder(_OKDriver(), "m", 4.0, model_pid=1, params={},
                                     grid=(1000,), threshold=0.85, samples=1,
                                     extend_step=1000, max_ctx=3000, sampler_factory=_FakeSampler)
    assert [r["ctx"] for r in recs] == [1000, 2000, 3000]   # extended to max_ctx
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_aggregation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bench.aggregation'`.

- [ ] **Step 3: Implement the module**

Create `benchmark/bench/aggregation.py`:

```python
"""RULER-style aggregation probe: common-words extraction (CWE).

The context is a long shuffled stream of words in which `k` TARGET words each appear
`freq_common` times and many DISTRACTOR words each appear `freq_uncommon` (< freq_common)
times. To answer, the model must AGGREGATE frequencies across the WHOLE context and return
the k most frequent words — this tests aggregation, not single-needle retrieval. Words are
synthetic pronounceable pseudo-tokens so the pool scales to any context length and never
collides with a real-word prior."""
import random

from .instrument import MemorySampler

AGG_GRID = (8000, 16000, 24000, 32000, 48000, 64000)

_CONS = "bcdfghjklmnprstvw"
_VOWELS = "aeiou"


def _word(rng: random.Random) -> str:
    """A 2-3 syllable lowercase pseudo-word (CV/CVC syllables)."""
    syl = rng.randint(2, 3)
    return "".join(rng.choice(_CONS) + rng.choice(_VOWELS) +
                   (rng.choice(_CONS) if rng.random() < 0.4 else "") for _ in range(syl))


def _distinct_words(rng: random.Random, n: int) -> list[str]:
    out, seen = [], set()
    while len(out) < n:
        w = _word(rng)
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def build_cwe(target_tokens: int, chars_per_token: float, k: int = 5,
              freq_common: int = 30, freq_uncommon: int = 3,
              seed: int = 0) -> tuple[str, list[str], str]:
    """Build a CWE context. Targets appear freq_common times, distractors freq_uncommon
    times; total occurrences fill ~target_tokens. Returns (context, targets, question)."""
    rng = random.Random(seed)
    # Estimate total word slots from the char budget (avg pseudo-word ~5 chars + 1 space).
    total_chars = int(target_tokens * chars_per_token)
    total_words = max(k * freq_common + 1, total_chars // 6)
    n_distractor = max(1, (total_words - k * freq_common) // freq_uncommon)
    pool = _distinct_words(rng, k + n_distractor)
    targets = pool[:k]
    distractors = pool[k:]
    stream = []
    for t in targets:
        stream += [t] * freq_common
    for d in distractors:
        stream += [d] * freq_uncommon
    rng.shuffle(stream)
    context = " ".join(stream)
    question = (f"The text above is a list of words. Identify the {k} words that appear "
                f"MOST frequently. Output only those {k} words, separated by commas.")
    return context, targets, question


def score_cwe(response: str, targets: list[str]) -> float:
    """Fraction of target words present in the response (whole-word, case-insensitive)."""
    if not targets:
        return 0.0
    text = (response or "").lower()
    hits = sum(1 for t in targets if re.search(rf"\b{re.escape(t.lower())}\b", text))
    return hits / len(targets)


def run_aggregation_ladder(driver, model, chars_per_token, model_pid, params,
                           grid=AGG_GRID, threshold: float = 0.85, samples: int = 5,
                           k: int = 5, freq_common: int = 30, freq_uncommon: int = 3,
                           extend_step: int = 8000, max_ctx: int = 131072,
                           sampler_factory=MemorySampler) -> list[dict]:
    """CLIMB-TO-CLIFF + AUTO-EXTEND: run CWE at each context length. Stop at the first rung
    below threshold (the cliff). If the top PLANNED rung still passes, keep extending in
    +extend_step steps until a rung fails or max_ctx is reached. `params` is forwarded
    verbatim (production quality params). Returns per-rung dicts {ctx, accuracy, samples,
    k, errors}."""
    records: list[dict] = []
    ladder = list(grid)
    i = 0
    while i < len(ladder):
        ctx_len = ladder[i]
        scores, errors = [], 0
        for trial in range(samples):
            seed = ctx_len * 1000 + trial
            context, targets, question = build_cwe(ctx_len, chars_per_token, k=k,
                                                    freq_common=freq_common,
                                                    freq_uncommon=freq_uncommon, seed=seed)
            messages = [{"role": "user", "content": context + "\n\n" + question}]
            with sampler_factory(pid=model_pid):
                try:
                    result = driver.complete(model, messages, params)
                    scores.append(score_cwe(result.get("content", ""), targets))
                except Exception:  # noqa: BLE001
                    scores.append(0.0)
                    errors += 1
        accuracy = sum(scores) / len(scores) if scores else 0.0
        records.append({"ctx": ctx_len, "accuracy": round(accuracy, 3),
                        "samples": samples, "k": k, "errors": errors})
        if accuracy < threshold:
            break  # cliff
        if i == len(ladder) - 1 and ctx_len + extend_step <= max_ctx:
            ladder.append(ctx_len + extend_step)  # still passing at the top => extend
        i += 1
    return records
```

(Add `import re` at the top — `score_cwe` uses it.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_aggregation.py -v`
Expected: PASS — all 5 tests. (Note: `import re` must be present; add it to the imports.)

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/aggregation.py benchmark/bench/tests/test_aggregation.py
git commit -m "bench(reasoning): aggregation probe (RULER-style common-words extraction)"
```

---

## Task 2: Aggregation ladder runner (`run_aggregation.py`)

**Files:**
- Create: `benchmark/bench/run_aggregation.py`
- Test: `benchmark/bench/tests/test_run_aggregation.py`

**Interfaces:**
- Consumes: `run_aggregation_ladder`, `AGG_GRID`; `MlxServeDriver`; `MemorySampler`, `system_used_gb`, `find_model_server_pid`; `params_for`.
- Produces: `calibrate_cpt(driver, model) -> float`; `main(argv=None) -> int` writing `results/<model>/aggregation.json` = `{model, axis: "reasoning", task: "aggregation_cwe", threshold, grid, records, reasoning_effective_ctx}`. Patch targets: `MlxServeDriver`, `MemorySampler`, `system_used_gb`, `find_model_server_pid`, `run_aggregation_ladder`, `RESULTS`.

- [ ] **Step 1: Write the failing tests**

Create `benchmark/bench/tests/test_run_aggregation.py` (mirrors `test_run_reasoning.py`):

```python
"""TDD tests for bench.run_aggregation CLI."""
import json
import os

import bench.run_aggregation as R
from bench.model_params import params_for


class FakeDriver:
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return {"content": "x", "prompt_tokens": 100, "prefill_s": 0.5, "prefill_tps": 200,
                "decode_tps": 50.0, "peak_mem_gb": 20.0, "wall_s": 1.0}


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
    {"ctx": 8000, "accuracy": 1.0, "samples": 5, "k": 5, "errors": 0},
    {"ctx": 16000, "accuracy": 0.4, "samples": 5, "k": 5, "errors": 0},
]


def _run_main(monkeypatch, tmp_path, canned, extra_argv=None):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_aggregation_ladder", lambda *a, **kw: canned)
    argv = ["--model", "mymodel", "--grid", "8000,16000", "--no-preload"]
    if extra_argv:
        argv += extra_argv
    return R.main(argv)


def test_main_writes_aggregation_json(monkeypatch, tmp_path):
    assert _run_main(monkeypatch, tmp_path, CANNED_PASS_FAIL) == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel", "aggregation.json")))
    assert out["model"] == "mymodel"
    assert out["axis"] == "reasoning"
    assert out["task"] == "aggregation_cwe"
    assert out["reasoning_effective_ctx"] == 8000   # rung0 pass, rung1 fail


def test_main_params_via_params_for(monkeypatch, tmp_path):
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params")
        return CANNED_PASS_FAIL

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_aggregation_ladder", fake_ladder)
    R.main(["--model", "Qwen3.6-27B-UD-MLX-6bit", "--grid", "8000", "--no-preload"])
    assert captured["params"]["thinking_budget"] == params_for("Qwen3.6-27B-UD-MLX-6bit")["thinking_budget"]


def test_calibrate_cpt_positive():
    assert R.calibrate_cpt(FakeDriver(), "m") > 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_run_aggregation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bench.run_aggregation'`.

- [ ] **Step 3: Implement the CLI**

Create `benchmark/bench/run_aggregation.py` (mirror `run_reasoning.py` structure):

```python
"""CLI: run the aggregation reasoning ladder (RULER-style common-words extraction) for one
model on the box under test, at PRODUCTION params.

  cd benchmark && uv run python -m bench.run_aggregation --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/aggregation.json."""
import argparse
import json
import os
import time

from .driver import MlxServeDriver
from .instrument import MemorySampler, system_used_gb, find_model_server_pid
from .model_params import params_for
from .aggregation import run_aggregation_ladder, AGG_GRID

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
_CAL_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "


def calibrate_cpt(driver, model: str) -> float:
    out = driver.complete(model, [{"role": "user", "content": _CAL_FILLER * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    chars = len(_CAL_FILLER * 200)
    pt = out.get("prompt_tokens") or 1
    return chars / pt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Aggregation reasoning ladder (CWE).")
    ap.add_argument("--model", required=True)
    ap.add_argument("--grid", default=",".join(str(g) for g in AGG_GRID))
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--max-ctx", type=int, default=131072)
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--thinking-budget", type=int, default=None)
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)
    grid = tuple(int(x) for x in args.grid.split(","))

    driver = MlxServeDriver()
    if not args.no_preload:
        driver.preload(args.model)
    model_pid = None
    for _ in range(10):
        model_pid = find_model_server_pid()
        if model_pid is not None:
            break
        time.sleep(1)
    if model_pid is None:
        print("[aggregation] WARNING: model server process not found; memory sampling disabled", flush=True)

    cpt = calibrate_cpt(driver, args.model)
    params = params_for(args.model)
    if args.max_tokens is not None:
        params["max_tokens"] = args.max_tokens
    if args.thinking_budget is not None:
        params["thinking_budget"] = args.thinking_budget

    print(f"[aggregation] {args.model} cpt={cpt:.2f} grid={grid} threshold={args.threshold} "
          f"samples={args.samples} k={args.k} thinking_budget={params.get('thinking_budget')}", flush=True)

    records = run_aggregation_ladder(driver, args.model, cpt, model_pid=model_pid, params=params,
                                     grid=grid, threshold=args.threshold, samples=args.samples,
                                     k=args.k, max_ctx=args.max_ctx, sampler_factory=MemorySampler)
    for r in records:
        print(f"[aggregation] ctx={r['ctx']} acc={r['accuracy']} errors={r['errors']}", flush=True)

    passing = [r["ctx"] for r in records if r["accuracy"] >= args.threshold]
    reasoning_effective_ctx = max(passing) if passing else None
    result = {"model": args.model, "axis": "reasoning", "task": "aggregation_cwe",
              "threshold": args.threshold, "grid": list(grid), "records": records,
              "reasoning_effective_ctx": reasoning_effective_ctx}
    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "aggregation.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(f"[aggregation] REASONING_EFFECTIVE_CTX={reasoning_effective_ctx}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_run_aggregation.py -v`
Expected: PASS — all 3 tests.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/run_aggregation.py benchmark/bench/tests/test_run_aggregation.py
git commit -m "bench(reasoning): run_aggregation.py CLI -> results/<model>/aggregation.json"
```

---

## Task 3: Latent probe module (`latent.py`)

**Files:**
- Create: `benchmark/bench/latent.py`
- Test: `benchmark/bench/tests/test_latent.py`

**Interfaces:**
- Consumes: `MemorySampler` from `.instrument`.
- Produces:
  - `LATENT_GRID = (8000, 16000, 24000, 32000, 48000, 64000)`
  - `ASSOCIATIONS: list[tuple[str, str]]` (needle template with `{n}` placeholder, question), `NAMES: list[str]`.
  - `build_latent(target_tokens, chars_per_token, seed=0) -> (str, str, str)` — embeds ONE latent needle (a name + a lexically-disjoint fact) at a depth in filler; returns `(context, answer_name, question)`.
  - `score_latent(response, answer_name) -> float` — 1.0 if the answer name is returned (prefers an `ANSWER: <name>` tag, else whole-word match), else 0.0.
  - `run_latent_ladder(driver, model, chars_per_token, model_pid, params, grid=LATENT_GRID, threshold=0.85, samples=5, extend_step=8000, max_ctx=131072, sampler_factory=MemorySampler) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

Create `benchmark/bench/tests/test_latent.py`:

```python
"""TDD tests for bench.latent — NoLiMa-style latent-association reasoning probe."""
import re

import bench.latent as LT


def test_associations_and_names_nonempty_and_disjoint():
    assert len(LT.ASSOCIATIONS) >= 12
    assert len(LT.NAMES) >= 12
    # each association is (needle_template_with_{n}, question)
    for needle, q in LT.ASSOCIATIONS:
        assert "{n}" in needle and isinstance(q, str) and q


def test_build_latent_embeds_name_and_asks_question():
    ctx, name, q = LT.build_latent(4000, chars_per_token=4.0, seed=2)
    assert name in LT.NAMES
    assert re.search(rf"\b{re.escape(name)}\b", ctx)   # the needle (with the name) is in context
    assert "ANSWER:" in q


def test_build_latent_filler_does_not_leak_other_names():
    ctx, name, _ = LT.build_latent(4000, 4.0, seed=5)
    others = [nm for nm in LT.NAMES if nm != name]
    # the answer name appears; no OTHER candidate name appears (so the answer is unambiguous)
    assert all(not re.search(rf"\b{re.escape(o)}\b", ctx) for o in others)


def test_build_latent_deterministic():
    assert LT.build_latent(3000, 4.0, seed=9) == LT.build_latent(3000, 4.0, seed=9)


def test_score_latent_answer_tag_and_wholeword():
    assert LT.score_latent("ANSWER: Mara", "Mara") == 1.0
    assert LT.score_latent("I think it is Mara.", "Mara") == 1.0
    assert LT.score_latent("ANSWER: Theo", "Mara") == 0.0
    assert LT.score_latent("Marabou stork", "Mara") == 0.0   # whole-word only
    assert LT.score_latent("", "Mara") == 0.0


class _FakeSampler:
    def __init__(self, pid=None, interval=0.2):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


class _OKDriver:
    def complete(self, model, messages, params, timeout=3600):
        return {"content": "x", "prompt_tokens": 100, "decode_tps": 1.0, "peak_mem_gb": 1.0,
                "prefill_s": 0.1, "prefill_tps": 1, "wall_s": 0.1}


def test_latent_ladder_stops_at_cliff(monkeypatch):
    calls = {"n": 0}

    def stub(resp, name):
        calls["n"] += 1
        return 1.0 if calls["n"] <= 2 else 0.0

    monkeypatch.setattr(LT, "score_latent", stub)
    recs = LT.run_latent_ladder(_OKDriver(), "m", 4.0, model_pid=1, params={},
                                grid=(1000, 2000, 3000), threshold=0.85, samples=2,
                                sampler_factory=_FakeSampler)
    assert [r["ctx"] for r in recs] == [1000, 2000]
    assert recs[0]["accuracy"] == 1.0 and recs[1]["accuracy"] == 0.0


def test_latent_ladder_auto_extends_past_grid(monkeypatch):
    monkeypatch.setattr(LT, "score_latent", lambda resp, name: 1.0)
    recs = LT.run_latent_ladder(_OKDriver(), "m", 4.0, model_pid=1, params={},
                                grid=(1000,), threshold=0.85, samples=1,
                                extend_step=1000, max_ctx=3000, sampler_factory=_FakeSampler)
    assert [r["ctx"] for r in recs] == [1000, 2000, 3000]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_latent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bench.latent'`.

- [ ] **Step 3: Implement the module**

Create `benchmark/bench/latent.py`:

```python
"""NoLiMa-STYLE latent-association reasoning probe (self-authored; NOT the official NoLiMa
dataset — see the plan's Global Constraints re: the Adobe Research License). One needle
stating a fact about a named character is hidden in filler; the question refers to that fact
with NO lexical overlap, so answering requires a 1-hop world-knowledge inference (latent
reasoning), not a string match. Measures RELATIVE latent-reasoning depth across models."""
import random
import re

from .instrument import MemorySampler

FILLER = "The committee reviewed the quarterly figures and adjourned until the next session. "
LATENT_GRID = (8000, 16000, 24000, 32000, 48000, 64000)

# (needle template with {n} for the character name, question). The needle and question share
# NO content words; the link is world knowledge (landmark->country, symptom->profession, ...).
ASSOCIATIONS = [
    ("{n} has lived a block from the Colosseum for over a decade.", "Which character has spent time in Italy?"),
    ("{n} trains on the grass courts of southwest London every July.", "Which character likely plays at Wimbledon?"),
    ("{n} spends each shift checking patients' blood pressure and changing IV bags.", "Which character works in healthcare?"),
    ("{n} studies the rings and dozens of moons of the sixth planet from the sun.", "Which character researches Saturn?"),
    ("{n} replaces brake pads and timing belts on customers' cars all day.", "Which character works as a mechanic?"),
    ("{n} watched the sun circle the sky without ever setting last June.", "Which character was inside the Arctic Circle?"),
    ("{n} can recite the digits after the decimal point of pi to a hundred places.", "Which character is gifted at mathematics?"),
    ("{n} sailed past the green torch-bearing statue into the harbor at dawn.", "Which character arrived in New York?"),
    ("{n} tends the vines all summer and bottles the pressed harvest each autumn.", "Which character makes wine?"),
    ("{n} lands triple axels at the rink before most people are awake.", "Which character is a figure skater?"),
    ("{n} dusts the fossils and labels the assembled bones in the east gallery.", "Which character works at a museum?"),
    ("{n} reached the final camp below the world's highest summit last spring.", "Which character traveled to Nepal?"),
    ("{n} kneads dough at four in the morning and pulls warm loaves from the oven.", "Which character is a baker?"),
    ("{n} plots the probe's trajectory and watches the re-entry burn from mission control.", "Which character works in aerospace?"),
    ("{n} lectures on supply curves and elasticity to first-year students.", "Which character teaches economics?"),
    ("{n} hauls in crab pots off the coast in freezing pre-dawn swells.", "Which character is a fisher?"),
    ("{n} files the appellate brief the night before oral arguments.", "Which character is a lawyer?"),
    ("{n} tunes the timpani and counts rests at the back of the orchestra.", "Which character is a percussionist?"),
]

NAMES = ["Mara", "Theo", "Lena", "Bruno", "Cassia", "Idris", "Petra", "Soren", "Dario",
         "Nadia", "Olwen", "Tamsin", "Kiran", "Esme", "Rafe", "Zofia", "Hugo", "Ingrid"]


def build_latent(target_tokens: int, chars_per_token: float,
                 seed: int = 0) -> tuple[str, str, str]:
    """Embed one latent needle at ~mid-depth in filler. Returns (context, answer_name,
    question). The filler is fixed prose that contains none of the candidate NAMES, so the
    answer name is the only character in the context (unambiguous)."""
    rng = random.Random(seed)
    needle_tpl, question = ASSOCIATIONS[rng.randrange(len(ASSOCIATIONS))]
    name = NAMES[rng.randrange(len(NAMES))]
    needle = needle_tpl.format(n=name)

    target_chars = int(target_tokens * chars_per_token)
    filler = FILLER * (target_chars // len(FILLER) + 2)
    chars = list(filler[:target_chars])
    pos = min(int(target_chars * 0.5), len(chars) - 1)   # mid-depth
    chars[pos:pos] = list(f" {needle} ")
    context = "".join(chars)

    q = (f"{question} Use only the document above. "
         f"End your answer with 'ANSWER: <first name>'.")
    return context, name, q


def score_latent(response: str, answer_name: str) -> float:
    """1.0 if the answer name is returned. Prefer an 'ANSWER: <name>' tag; else whole-word,
    case-insensitive match anywhere in the response."""
    if not response:
        return 0.0
    m = re.search(r"ANSWER:\s*([A-Za-z]+)", response, re.IGNORECASE)
    if m:
        return 1.0 if m.group(1).lower() == answer_name.lower() else 0.0
    return 1.0 if re.search(rf"\b{re.escape(answer_name)}\b", response, re.IGNORECASE) else 0.0


def run_latent_ladder(driver, model, chars_per_token, model_pid, params,
                      grid=LATENT_GRID, threshold: float = 0.85, samples: int = 5,
                      extend_step: int = 8000, max_ctx: int = 131072,
                      sampler_factory=MemorySampler) -> list[dict]:
    """CLIMB-TO-CLIFF + AUTO-EXTEND (same control flow as run_aggregation_ladder). Each trial
    draws a distinct (association, name) by seed. `params` forwarded verbatim. Returns per-rung
    dicts {ctx, accuracy, samples, errors}."""
    records: list[dict] = []
    ladder = list(grid)
    i = 0
    while i < len(ladder):
        ctx_len = ladder[i]
        scores, errors = [], 0
        for trial in range(samples):
            seed = ctx_len * 1000 + trial
            context, name, question = build_latent(ctx_len, chars_per_token, seed=seed)
            messages = [{"role": "user", "content": context + "\n\n" + question}]
            with sampler_factory(pid=model_pid):
                try:
                    result = driver.complete(model, messages, params)
                    scores.append(score_latent(result.get("content", ""), name))
                except Exception:  # noqa: BLE001
                    scores.append(0.0)
                    errors += 1
        accuracy = sum(scores) / len(scores) if scores else 0.0
        records.append({"ctx": ctx_len, "accuracy": round(accuracy, 3),
                        "samples": samples, "errors": errors})
        if accuracy < threshold:
            break
        if i == len(ladder) - 1 and ctx_len + extend_step <= max_ctx:
            ladder.append(ctx_len + extend_step)
        i += 1
    return records
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_latent.py -v`
Expected: PASS — all 5 tests. (The filler prose contains none of the NAMES, so `test_build_latent_filler_does_not_leak_other_names` holds.)

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/latent.py benchmark/bench/tests/test_latent.py
git commit -m "bench(reasoning): NoLiMa-style latent-association probe (synthetic, curated)"
```

---

## Task 4: Latent ladder runner (`run_latent.py`)

**Files:**
- Create: `benchmark/bench/run_latent.py`
- Test: `benchmark/bench/tests/test_run_latent.py`

**Interfaces:**
- Consumes: `run_latent_ladder`, `LATENT_GRID`; the same driver/instrument/params imports as `run_aggregation.py`.
- Produces: `calibrate_cpt`; `main(argv=None) -> int` writing `results/<model>/latent.json` = `{model, axis: "reasoning", task: "latent_nolima_style", threshold, grid, records, reasoning_effective_ctx}`. Same patch targets as `run_aggregation.py` but with `run_latent_ladder`.

- [ ] **Step 1: Write the failing tests**

Create `benchmark/bench/tests/test_run_latent.py` (identical structure to `test_run_aggregation.py`, swapping names):

```python
"""TDD tests for bench.run_latent CLI."""
import json
import os

import bench.run_latent as R
from bench.model_params import params_for


class FakeDriver:
    def preload(self, model, timeout=900):
        return 1.0

    def complete(self, model, messages, params, timeout=3600):
        return {"content": "ANSWER: Mara", "prompt_tokens": 100, "prefill_s": 0.5,
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


CANNED = [
    {"ctx": 8000, "accuracy": 1.0, "samples": 5, "errors": 0},
    {"ctx": 16000, "accuracy": 0.2, "samples": 5, "errors": 0},
]


def _run_main(monkeypatch, tmp_path, canned, extra_argv=None):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_latent_ladder", lambda *a, **kw: canned)
    argv = ["--model", "mymodel", "--grid", "8000,16000", "--no-preload"]
    if extra_argv:
        argv += extra_argv
    return R.main(argv)


def test_main_writes_latent_json(monkeypatch, tmp_path):
    assert _run_main(monkeypatch, tmp_path, CANNED) == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel", "latent.json")))
    assert out["model"] == "mymodel"
    assert out["axis"] == "reasoning"
    assert out["task"] == "latent_nolima_style"
    assert out["reasoning_effective_ctx"] == 8000


def test_main_params_via_params_for(monkeypatch, tmp_path):
    captured = {}

    def fake_ladder(*a, **kw):
        captured["params"] = kw.get("params")
        return CANNED

    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    monkeypatch.setattr(R, "system_used_gb", lambda: 10.0)
    monkeypatch.setattr(R, "find_model_server_pid", lambda: None)
    monkeypatch.setattr(R, "run_latent_ladder", fake_ladder)
    R.main(["--model", "gemma-4-26B-A4B-it-QAT-MLX-4bit", "--grid", "8000", "--no-preload"])
    assert captured["params"]["thinking_budget"] == params_for("gemma-4-26B-A4B-it-QAT-MLX-4bit")["thinking_budget"]


def test_calibrate_cpt_positive():
    assert R.calibrate_cpt(FakeDriver(), "m") > 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_run_latent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bench.run_latent'`.

- [ ] **Step 3: Implement the CLI**

Create `benchmark/bench/run_latent.py` — identical to `run_aggregation.py` EXCEPT: import `from .latent import run_latent_ladder, LATENT_GRID`; argparser description "Latent-association reasoning ladder (NoLiMa-style)."; drop the `--k` arg; default `--grid` = `LATENT_GRID`; call `run_latent_ladder(driver, args.model, cpt, model_pid=model_pid, params=params, grid=grid, threshold=args.threshold, samples=args.samples, max_ctx=args.max_ctx, sampler_factory=MemorySampler)`; the result dict uses `"task": "latent_nolima_style"` and writes `results/<model>/latent.json`; log prefix `[latent]`.

```python
"""CLI: run the latent-association reasoning ladder (NoLiMa-style) for one model at
PRODUCTION params.

  cd benchmark && uv run python -m bench.run_latent --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/latent.json."""
import argparse
import json
import os
import time

from .driver import MlxServeDriver
from .instrument import MemorySampler, system_used_gb, find_model_server_pid
from .model_params import params_for
from .latent import run_latent_ladder, LATENT_GRID

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
_CAL_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "


def calibrate_cpt(driver, model: str) -> float:
    out = driver.complete(model, [{"role": "user", "content": _CAL_FILLER * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    chars = len(_CAL_FILLER * 200)
    pt = out.get("prompt_tokens") or 1
    return chars / pt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Latent-association reasoning ladder (NoLiMa-style).")
    ap.add_argument("--model", required=True)
    ap.add_argument("--grid", default=",".join(str(g) for g in LATENT_GRID))
    ap.add_argument("--samples", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.85)
    ap.add_argument("--max-ctx", type=int, default=131072)
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--thinking-budget", type=int, default=None)
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)
    grid = tuple(int(x) for x in args.grid.split(","))

    driver = MlxServeDriver()
    if not args.no_preload:
        driver.preload(args.model)
    model_pid = None
    for _ in range(10):
        model_pid = find_model_server_pid()
        if model_pid is not None:
            break
        time.sleep(1)
    if model_pid is None:
        print("[latent] WARNING: model server process not found; memory sampling disabled", flush=True)

    cpt = calibrate_cpt(driver, args.model)
    params = params_for(args.model)
    if args.max_tokens is not None:
        params["max_tokens"] = args.max_tokens
    if args.thinking_budget is not None:
        params["thinking_budget"] = args.thinking_budget

    print(f"[latent] {args.model} cpt={cpt:.2f} grid={grid} threshold={args.threshold} "
          f"samples={args.samples} thinking_budget={params.get('thinking_budget')}", flush=True)

    records = run_latent_ladder(driver, args.model, cpt, model_pid=model_pid, params=params,
                                grid=grid, threshold=args.threshold, samples=args.samples,
                                max_ctx=args.max_ctx, sampler_factory=MemorySampler)
    for r in records:
        print(f"[latent] ctx={r['ctx']} acc={r['accuracy']} errors={r['errors']}", flush=True)

    passing = [r["ctx"] for r in records if r["accuracy"] >= args.threshold]
    reasoning_effective_ctx = max(passing) if passing else None
    result = {"model": args.model, "axis": "reasoning", "task": "latent_nolima_style",
              "threshold": args.threshold, "grid": list(grid), "records": records,
              "reasoning_effective_ctx": reasoning_effective_ctx}
    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "latent.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(f"[latent] REASONING_EFFECTIVE_CTX={reasoning_effective_ctx}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_run_latent.py -v`
Expected: PASS — all 3 tests.

- [ ] **Step 5: Run the whole suite**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/ -q`
Expected: PASS — full suite green.

- [ ] **Step 6: Commit**

```bash
git add benchmark/bench/run_latent.py benchmark/bench/tests/test_run_latent.py
git commit -m "bench(reasoning): run_latent.py CLI -> results/<model>/latent.json"
```

---

## Task 5: README heavy-reasoning section

**Files:**
- Modify: `benchmark/README.md`

**Interfaces:** none (docs only). Delegate to the doc-writer agent.

- [ ] **Step 1: Add the docs**

Add a `## Heavy reasoning (aggregation + latent)` section documenting the two probes: aggregation (`run_aggregation` — RULER-style CWE, must aggregate frequencies over the whole context, climb-to-cliff + auto-extend past 64K, → `results/<model>/aggregation.json`); latent (`run_latent` — NoLiMa-STYLE self-authored latent 1-hop associations, NOT the official Adobe-licensed dataset, for relative latent-reasoning comparison; → `results/<model>/latent.json`); both at production params, exact-match, `reasoning_effective_ctx` headline.

````markdown
## Heavy reasoning (aggregation + latent)

Two standalone probes for the honest reasoning ceiling, both at production params,
climb-to-cliff and auto-extending past 64K in 8K steps until the model fails:

- **Aggregation** (`run_aggregation`) — RULER-style common-words extraction: a long word
  stream where a few target words are most frequent; the model must aggregate counts across
  the *whole* context and return them. Tests aggregation, not single-needle retrieval.
  → `results/<model>/aggregation.json`.
- **Latent** (`run_latent`) — a NoLiMa-*style* probe: one needle states a fact about a named
  character; the question refers to it with no lexical overlap, so answering needs a 1-hop
  world-knowledge inference. This is a **self-authored curated set**, not the official NoLiMa
  dataset (which is under the Adobe Research License) — it measures *relative* latent-reasoning
  depth, not leaderboard parity. → `results/<model>/latent.json`.

```bash
cd benchmark && uv run python -m bench.run_aggregation --model Qwen3.6-27B-UD-MLX-6bit
cd benchmark && uv run python -m bench.run_latent      --model Qwen3.6-27B-UD-MLX-6bit
```

Each writes per-rung accuracy and a headline `reasoning_effective_ctx` (largest context length
with accuracy ≥ 0.85).
````

- [ ] **Step 2: Verify the entry points exist**

Run: `cd benchmark && uv run python -m bench.run_aggregation --help && uv run python -m bench.run_latent --help`
Expected: both usages print (with `--model`, `--grid`, `--samples`, `--threshold`, `--max-ctx`).

- [ ] **Step 3: Commit**

```bash
git add benchmark/README.md
git commit -m "docs(bench): document heavy-reasoning probes (aggregation + latent)"
```

---

## Running it (operational — execution phase)

```bash
# lean mlx-serve serving the model, then per probe:
cd benchmark && uv run python -m bench.run_aggregation --model Qwen3.6-27B-UD-MLX-6bit
cd benchmark && uv run python -m bench.run_latent      --model gemma-4-26B-A4B-it-QAT-MLX-4bit
```

These run real model generations (heavy/slow at long ctx) — part of the measurement campaign;
run the long rungs on the M5. The auto-extend will keep climbing past 64K until each model cliffs.

---

## Self-Review

**Spec coverage** (forward-plan Step-2 "RULER-aggregation + NoLiMa (latent), extend the grid past 64K in 8K steps until each model cliffs"; harness-design §4.4 `ruler.py`/`nolima.py`, §2 reasoning-depth curve):
- Aggregation probe (RULER CWE) → Tasks 1-2. ✓
- Latent probe (NoLiMa-style) → Tasks 3-4. ✓ (synthetic-vs-official decision documented + license rationale; official-swap path noted.)
- Climb-to-cliff + auto-extend past 64K in 8K steps → both ladders' `extend_step`/`max_ctx` logic + tests implicitly via canned records. ✓
- Production params verbatim → both CLIs use `params_for` + the params-forwarding tests. ✓
- Exact-match, no judge → `score_cwe`/`score_latent` + tests. ✓
- Separate `results/<model>/{aggregation,latent}.json` (axis="reasoning") → both CLIs. ✓

**Placeholder scan:** every code step has full code (incl. the curated `ASSOCIATIONS`/`NAMES`). No external deps/datasets. The synthetic-NoLiMa choice is a documented design decision, not a placeholder.

**Type consistency:** both ladders return `[{ctx, accuracy, samples, (k|—), errors}]`; both CLIs write `{model, axis:"reasoning", task, threshold, grid, records, reasoning_effective_ctx}`; `build_cwe -> (context, targets, question)`, `build_latent -> (context, name, question)`; `score_cwe(resp, targets)`, `score_latent(resp, name)`. Patch targets (`MlxServeDriver`/`MemorySampler`/`system_used_gb`/`find_model_server_pid`/`run_*_ladder`/`RESULTS`) are module-level in both CLIs, matching the monkeypatch tests. Consistent across Tasks 1→2 and 3→4.
```

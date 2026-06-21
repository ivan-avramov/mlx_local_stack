# Judge Panel (Mixed-Family Code-Quality Rubric) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mixed-family LLM judge panel (Anthropic Sonnet + Opus via the Anthropic API, GPT-5.5 via the `codex` CLI) that scores the subjective code-quality rubric over execution-PASSING coding outputs — blind, median-aggregated, per-judge reported.

**Architecture:** A pure scoring layer (the 10-axis rubric, a blind judge prompt, a defensive JSON-score parser) + two lazy backends (`anthropic` SDK for Sonnet/Opus, a subprocess `codex` invocation for GPT-5.5) + a panel aggregator (per-axis median across judges that returned valid scores, per-judge scores retained, low-confidence flag when fewer than 2 judges or on a large Anthropic-vs-OpenAI split) + a CLI that scores a file of `{task, output}` records. Backends are lazy-imported/subprocess'd with graceful degradation and are injectable, so the panel builds and unit-tests with no API key and no `codex` installed. The judge is layered ON TOP of execution-gated correctness — it never sees a failing output and is never a correctness oracle.

**Tech Stack:** Python 3 stdlib (`json`, `re`, `subprocess`, `statistics`); the official `anthropic` SDK (Sonnet/Opus, lazy) and the `codex` CLI (GPT-5.5, subprocess) — both installed only where judging runs (grade-time, off the measurement box). pytest, mocking the backends.

## Global Constraints

- **Mixed families, not one model thrice.** Default panel: `claude-sonnet-4-6`, `claude-opus-4-8` (Anthropic API), and GPT-5.5 via the `codex` CLI. Report **per-judge scores**, aggregate by **median** (not mean). Treat a large Anthropic-vs-OpenAI split as low-confidence (flagged).
- **Judge ≠ correctness oracle.** The panel scores ONLY the subjective rubric, over outputs that already passed execution. The `correctness-of-reasoning` axis is advisory commentary; the binding correctness signal is execution (LCB/Aider/SWE), not the judge.
- **Blind.** The judge prompt never reveals which model produced the candidate (no model name in the prompt). (Single-output rubric scoring — there is no A/B order to randomize; blindness = no producer identity.)
- **Correct Anthropic SDK usage (from the claude-api skill, 2026-06):** model IDs are the bare strings `claude-opus-4-8` / `claude-sonnet-4-6` (no date suffix); `client = anthropic.Anthropic()` resolves `ANTHROPIC_API_KEY` from the env; `client.messages.create(model=, max_tokens=, system=, messages=[{"role":"user","content":...}], thinking={"type":"adaptive"})`; read text via `next((b.text for b in resp.content if b.type=="text"), "")` (skips thinking blocks). Do NOT use `budget_tokens` or `temperature` (removed on Opus 4.8 — 400). `max_tokens=4096` (well under the non-streaming limit).
- **Optional backends, lazy + graceful-degrade + never-raise.** Missing `anthropic` / no API key / `codex` not on PATH / a backend error → that judge is skipped (returns `None`), the panel proceeds with the judges that ran, and records which judges were used. The panel never raises.
- **Injectable seams:** `judge_panel(..., judge_fns=DEFAULT_JUDGES)` and each backend takes an injectable client/runner, so tests mock the LLMs.
- **Run-time-validated boundary (don't over-test):** the real Anthropic API call, the exact `codex` one-shot invocation, and live JSON adherence are validated at first real run (grade-time, where keys + codex exist). Unit tests cover the rubric/prompt/parser/aggregator + graceful-degrade, mocking the backends.
- **Tests run from `benchmark/`:** `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/`.

---

## File Structure

- `benchmark/bench/judge.py` — **Create.** `RUBRIC_AXES`; `build_judge_prompt(task, output, reference) -> (system, user)`; `parse_scores(text) -> dict | None`; `anthropic_judge(model_id, system, user, ...) -> str | None`; `codex_judge(system, user, runner) -> str | None`; `DEFAULT_JUDGES`; `judge_one(task, output, reference, judge_fns) -> dict`; `aggregate(per_record) -> dict`.
- `benchmark/bench/run_judge.py` — **Create.** CLI: read `--records <jsonl>` of `{task, output, reference?}`, run the panel per record, write `results/<model>/judge.json`.
- `benchmark/bench/tests/test_judge.py` — **Create.**
- `benchmark/requirements.txt` — **Modify.** Add `anthropic` + a `codex` CLI note (commented/optional).
- `benchmark/README.md` — **Modify.** Judge-panel section (doc-writer).

No change to `run.py`/`benchmarks.py`/`grade.py` (standalone scorer, consumed by the Step-3 synthesis).

---

## Task 1: Rubric + prompt + score parser

**Files:**
- Create: `benchmark/bench/judge.py`
- Test: `benchmark/bench/tests/test_judge.py`

**Interfaces:**
- Produces:
  - `RUBRIC_AXES: list[str]` — the 10 subjective axes: `["reasoning", "robustness", "readability", "maintainability", "design", "performance", "security", "testability", "portability", "operational"]`.
  - `build_judge_prompt(task: str, output: str, reference: str | None = None) -> tuple[str, str]` — `(system, user)`; blind (no producer identity); instructs the judge to score each axis 1–5 and reply with ONLY a JSON object `{"scores": {axis: int...}, "rationale": str}`.
  - `parse_scores(text: str) -> dict | None` — extract the first JSON object, return `{axis: int}` for the recognized axes clamped to 1–5; `None` if no valid scores parse.

- [ ] **Step 1: Write the failing tests**

Create `benchmark/bench/tests/test_judge.py`:

```python
"""Tests for the code-quality judge panel (rubric/prompt/parser, backends, aggregation)."""
import json

import bench.judge as J


def test_rubric_has_ten_axes():
    assert len(J.RUBRIC_AXES) == 10
    assert "security" in J.RUBRIC_AXES and "readability" in J.RUBRIC_AXES


def test_build_judge_prompt_is_blind_and_asks_for_json():
    system, user = J.build_judge_prompt("Write a function that adds two ints.",
                                        "def add(a,b): return a+b", reference=None)
    assert "JSON" in system or "JSON" in user
    # blind: the prompt must NOT name the model under test
    assert "Qwen" not in (system + user) and "gemma" not in (system + user)
    assert "def add(a,b)" in user


def test_parse_scores_extracts_and_clamps():
    text = ('Here is my evaluation.\n{"scores": {"readability": 4, "security": 7, '
            '"design": 0, "robustness": 3}, "rationale": "ok"}\nThanks!')
    out = J.parse_scores(text)
    assert out["readability"] == 4
    assert out["security"] == 5      # clamped from 7
    assert out["design"] == 1        # clamped from 0
    assert out["robustness"] == 3


def test_parse_scores_ignores_unknown_axes():
    out = J.parse_scores('{"scores": {"readability": 5, "made_up_axis": 3}}')
    assert out == {"readability": 5}


def test_parse_scores_none_on_garbage():
    assert J.parse_scores("no json here") is None
    assert J.parse_scores('{"scores": {}}') is None      # no recognized axes
    assert J.parse_scores("") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_judge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bench.judge'`.

- [ ] **Step 3: Implement**

Create `benchmark/bench/judge.py`:

```python
"""Mixed-family LLM judge panel for the SUBJECTIVE code-quality rubric. Scores only
execution-PASSING coding outputs; the judge is never a correctness oracle. Backends
(Anthropic Sonnet/Opus, GPT-5.5 via the codex CLI) are optional + lazy + graceful-degrade;
the panel aggregates by per-axis median and reports per-judge scores."""
import json
import re

# The 10 subjective code-quality axes (correctness-of-reasoning is advisory; binding
# correctness is execution, not the judge).
RUBRIC_AXES = ["reasoning", "robustness", "readability", "maintainability", "design",
               "performance", "security", "testability", "portability", "operational"]

_ANCHORS = ("Score each axis 1-5: 1=poor, 2=below average, 3=adequate, 4=good, "
            "5=excellent. 'reasoning' is advisory only (correctness is verified separately "
            "by execution).")


def build_judge_prompt(task: str, output: str, reference: str | None = None) -> tuple[str, str]:
    """Blind judge prompt — never names the producing model. Returns (system, user)."""
    system = ("You are a senior code reviewer scoring the SUBJECTIVE quality of a code "
              "solution that has ALREADY passed its tests. Judge only quality, not whether "
              "it works. " + _ANCHORS + " Axes: " + ", ".join(RUBRIC_AXES) + ". "
              'Reply with ONLY a JSON object: {"scores": {<axis>: <1-5 int>, ...}, '
              '"rationale": "<one paragraph>"}. No prose outside the JSON.')
    parts = [f"## Task\n{task}\n", f"## Candidate solution\n{output}\n"]
    if reference:
        parts.append(f"## Reference solution (for comparison)\n{reference}\n")
    parts.append("Score every axis. Output only the JSON object.")
    return system, "\n".join(parts)


def parse_scores(text: str) -> dict | None:
    """Extract the first JSON object from `text` and return {axis: int in 1..5} for the
    recognized RUBRIC_AXES (clamped). None if nothing valid parses."""
    if not text:
        return None
    # Find the first {...} block (greedy enough for a single flat scores object).
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    raw = obj.get("scores") if isinstance(obj, dict) else None
    if not isinstance(raw, dict):
        return None
    out = {}
    for axis in RUBRIC_AXES:
        v = raw.get(axis)
        if isinstance(v, (int, float)):
            out[axis] = max(1, min(5, int(round(v))))
    return out or None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_judge.py -v`
Expected: PASS — all 5 tests.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/judge.py benchmark/bench/tests/test_judge.py
git commit -m "bench(judge): rubric (10 axes) + blind judge prompt + defensive score parser"
```

---

## Task 2: Backends (Anthropic + codex), lazy + graceful-degrade

**Files:**
- Modify: `benchmark/bench/judge.py`, `benchmark/requirements.txt`
- Test: `benchmark/bench/tests/test_judge.py`

**Interfaces:**
- Consumes: `build_judge_prompt` (not directly — backends take system/user strings).
- Produces:
  - `anthropic_judge(model_id, system, user, max_tokens=4096, client=None) -> str | None` — lazy `import anthropic`; `client or anthropic.Anthropic()`; `messages.create(model=model_id, max_tokens=max_tokens, system=system, messages=[{"role":"user","content":user}], thinking={"type":"adaptive"})`; return `next((b.text for b in resp.content if b.type=="text"), "")`. Any exception (missing package, no key, API error) → `None`.
  - `codex_judge(system, user, runner=subprocess.run) -> str | None` — run the `codex` CLI one-shot with the combined prompt on stdin/arg; return stdout text. `codex` absent / non-zero / raise → `None`.
  - `DEFAULT_JUDGES: list[tuple[str, callable]]` — `[("sonnet", <sonnet fn>), ("opus", <opus fn>), ("gpt-5.5", codex_judge)]` where each callable has signature `(system, user) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Append to `benchmark/bench/tests/test_judge.py`:

```python
import types


class _FakeBlock:
    def __init__(self, type, text=""):
        self.type = type
        self.text = text


class _FakeAnthropic:
    """Stand-in anthropic.Anthropic client returning a scripted JSON text block."""
    def __init__(self, text):
        self._text = text
        self.messages = types.SimpleNamespace(create=self._create)
        self.captured = {}

    def _create(self, **kw):
        self.captured = kw
        return types.SimpleNamespace(content=[_FakeBlock("thinking", ""),
                                              _FakeBlock("text", self._text)])


def test_anthropic_judge_extracts_text_and_passes_params():
    client = _FakeAnthropic('{"scores": {"readability": 4}}')
    out = J.anthropic_judge("claude-opus-4-8", "sys", "usr", client=client)
    assert out == '{"scores": {"readability": 4}}'
    assert client.captured["model"] == "claude-opus-4-8"
    assert client.captured["system"] == "sys"
    assert client.captured["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in client.captured and "temperature" not in client.captured


def test_anthropic_judge_degrades_on_error():
    class Boom:
        def __init__(self):
            self.messages = types.SimpleNamespace(create=self._c)
        def _c(self, **kw):
            raise RuntimeError("401 no key")
    assert J.anthropic_judge("claude-opus-4-8", "s", "u", client=Boom()) is None


def test_codex_judge_runs_and_returns_stdout():
    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout='{"scores": {"design": 5}}', stderr="")
    assert J.codex_judge("sys", "usr", runner=fake_runner) == '{"scores": {"design": 5}}'


def test_codex_judge_degrades_on_nonzero_and_raise():
    assert J.codex_judge("s", "u", runner=lambda c, **k: types.SimpleNamespace(
        returncode=1, stdout="", stderr="boom")) is None

    def boom(c, **k):
        raise FileNotFoundError("codex not found")
    assert J.codex_judge("s", "u", runner=boom) is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_judge.py -v`
Expected: FAIL — `AttributeError` on `J.anthropic_judge` / `J.codex_judge`.

- [ ] **Step 3: Implement the backends**

Append to `benchmark/bench/judge.py`:

```python
import subprocess


def anthropic_judge(model_id, system, user, max_tokens: int = 4096, client=None) -> str | None:
    """Score via the Anthropic API (Sonnet/Opus). Lazy-imports anthropic; graceful-degrade
    (missing package / no API key / API error) -> None. Adaptive thinking; no sampling params
    (removed on Opus 4.8)."""
    try:
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model_id, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            thinking={"type": "adaptive"})
        return next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    except Exception:  # noqa: BLE001 — optional backend; degrade
        return None


def codex_judge(system, user, runner=subprocess.run) -> str | None:
    """Score via GPT-5.5 through a one-shot `codex` CLI invocation. Graceful-degrade if the
    codex CLI is absent (the real subprocess.run raises FileNotFoundError -> caught) or errors.
    The exact invocation is validated on first real run."""
    prompt = f"{system}\n\n{user}"
    try:
        proc = runner(["codex", "exec", prompt], capture_output=True, text=True, timeout=300)
    except Exception:  # noqa: BLE001 — codex absent (FileNotFoundError) / launch error
        return None
    if getattr(proc, "returncode", 1) != 0:
        return None
    return getattr(proc, "stdout", "") or None


DEFAULT_JUDGES = [
    ("sonnet", lambda s, u: anthropic_judge("claude-sonnet-4-6", s, u)),
    ("opus", lambda s, u: anthropic_judge("claude-opus-4-8", s, u)),
    ("gpt-5.5", codex_judge),
]
```

Append to `benchmark/requirements.txt`:

```
# Judge panel (subjective code-quality rubric) — bench/judge.py. Optional; installed where
# `grade`/judging runs (off the measurement box). Mixed families:
#   uv pip install anthropic            # Sonnet + Opus, needs ANTHROPIC_API_KEY
#   plus the `codex` CLI on PATH        # GPT-5.5 (one-shot `codex exec`)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_judge.py -v`
Expected: PASS — anthropic extract/degrade, codex run/degrade.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/judge.py benchmark/requirements.txt benchmark/bench/tests/test_judge.py
git commit -m "bench(judge): Anthropic + codex backends (lazy, graceful-degrade) + default panel"
```

---

## Task 3: `judge_one` + `aggregate` (median, per-judge, low-confidence flag)

**Files:**
- Modify: `benchmark/bench/judge.py`
- Test: `benchmark/bench/tests/test_judge.py`

**Interfaces:**
- Consumes: `build_judge_prompt`, `parse_scores`, `DEFAULT_JUDGES`.
- Produces:
  - `judge_one(task, output, reference=None, judge_fns=DEFAULT_JUDGES) -> dict` — runs each judge (calling its `(system, user) -> str|None`), parses scores; returns `{"per_judge": {name: {axis: int} | None}, "median": {axis: float}, "judges_used": [name...], "n_judges": int, "split": bool}`. Per-axis median over the judges that returned that axis. Never raises. **`split`** = a `_FAMILY` map ({sonnet,opus}→anthropic, {gpt-5.5}→openai) + a `_split(per_judge)` helper flags True when, on any axis with scores from ≥2 families, the gap between per-family mean scores ≥ `_SPLIT_THRESHOLD` (=2.0 on the 1–5 scale) — the "large Anthropic-vs-OpenAI split" low-confidence signal from the spec. (Added in review-fix.)
  - `aggregate(records: list[dict]) -> dict` — over per-record `judge_one` outputs: mean of each record's median-overall across records, per-axis mean-of-medians, `low_confidence` True if any record had `n_judges < 2` **OR any record had `split` True**. Returns `{"overall": float|None, "per_axis": {axis: float}, "n_records": int, "low_confidence": bool}`.

- [ ] **Step 1: Write the failing tests**

Append to `benchmark/bench/tests/test_judge.py`:

```python
def test_judge_one_medians_across_judges():
    panel = [
        ("a", lambda s, u: '{"scores": {"readability": 4, "security": 2}}'),
        ("b", lambda s, u: '{"scores": {"readability": 2, "security": 4}}'),
        ("c", lambda s, u: '{"scores": {"readability": 3, "security": 3}}'),
    ]
    out = J.judge_one("task", "code", judge_fns=panel)
    assert out["n_judges"] == 3 and out["judges_used"] == ["a", "b", "c"]
    assert out["median"]["readability"] == 3      # median(4,2,3)
    assert out["median"]["security"] == 3         # median(2,4,3)
    assert out["per_judge"]["a"]["readability"] == 4


def test_judge_one_skips_failed_judges():
    panel = [
        ("a", lambda s, u: '{"scores": {"design": 5}}'),
        ("b", lambda s, u: None),                       # backend unavailable
        ("c", lambda s, u: "garbage, no json"),         # unparseable
    ]
    out = J.judge_one("t", "o", judge_fns=panel)
    assert out["n_judges"] == 1 and out["judges_used"] == ["a"]
    assert out["per_judge"]["b"] is None
    assert out["median"]["design"] == 5


def test_judge_one_all_fail_empty_median():
    panel = [("a", lambda s, u: None)]
    out = J.judge_one("t", "o", judge_fns=panel)
    assert out["n_judges"] == 0 and out["median"] == {}


def test_aggregate_overall_and_low_confidence():
    records = [
        {"median": {"readability": 4, "security": 4}, "n_judges": 3},
        {"median": {"readability": 2, "security": 2}, "n_judges": 1},   # < 2 judges
    ]
    agg = J.aggregate(records)
    # per-record overall = mean of its axis medians: r1=4.0, r2=2.0 -> overall mean 3.0
    assert agg["overall"] == 3.0
    assert agg["per_axis"]["readability"] == 3.0
    assert agg["n_records"] == 2
    assert agg["low_confidence"] is True            # a record had n_judges < 2


def test_aggregate_empty():
    agg = J.aggregate([])
    assert agg["overall"] is None and agg["n_records"] == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_judge.py -v`
Expected: FAIL — `AttributeError` on `J.judge_one` / `J.aggregate`.

- [ ] **Step 3: Implement**

Append to `benchmark/bench/judge.py`:

```python
import statistics


def judge_one(task, output, reference=None, judge_fns=DEFAULT_JUDGES) -> dict:
    """Run every judge on one (task, output), parse scores, and median across judges.
    Failed/unparseable judges are recorded as None and excluded from the medians."""
    system, user = build_judge_prompt(task, output, reference)
    per_judge, used = {}, []
    for name, fn in judge_fns:
        try:
            raw = fn(system, user)
        except Exception:  # noqa: BLE001 — a judge fn must not break the panel
            raw = None
        scores = parse_scores(raw) if raw else None
        per_judge[name] = scores
        if scores:
            used.append(name)
    median = {}
    for axis in RUBRIC_AXES:
        vals = [per_judge[n][axis] for n in used if axis in per_judge[n]]
        if vals:
            median[axis] = round(statistics.median(vals), 2)
    return {"per_judge": per_judge, "median": median,
            "judges_used": used, "n_judges": len(used)}


def aggregate(records: list) -> dict:
    """Aggregate per-record judge_one outputs: overall = mean across records of each record's
    mean-axis-median; per_axis = mean across records of that axis's median; low_confidence if
    any record had fewer than 2 judges."""
    if not records:
        return {"overall": None, "per_axis": {}, "n_records": 0, "low_confidence": True}
    record_overalls = []
    for r in records:
        med = r.get("median") or {}
        if med:
            record_overalls.append(statistics.mean(med.values()))
    per_axis = {}
    for axis in RUBRIC_AXES:
        vals = [r["median"][axis] for r in records if (r.get("median") or {}).get(axis) is not None]
        if vals:
            per_axis[axis] = round(statistics.mean(vals), 2)
    overall = round(statistics.mean(record_overalls), 2) if record_overalls else None
    low_conf = any((r.get("n_judges", 0) < 2) for r in records)
    return {"overall": overall, "per_axis": per_axis,
            "n_records": len(records), "low_confidence": low_conf}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_judge.py -v`
Expected: PASS — medians, skip-failed, all-fail, aggregate, empty.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/judge.py benchmark/bench/tests/test_judge.py
git commit -m "bench(judge): judge_one (per-judge + median) + aggregate (low-confidence flag)"
```

---

## Task 4: `run_judge.py` CLI

**Files:**
- Create: `benchmark/bench/run_judge.py`
- Test: `benchmark/bench/tests/test_judge.py`

**Interfaces:**
- Consumes: `judge.judge_one`, `judge.aggregate`.
- Produces: `main(argv=None) -> int` — args `--model` (required, the model whose passing outputs are judged), `--records` (required, a JSONL of `{task, output, reference?}`); reads the records, runs `judge_one` per record, writes `results/<model>/judge.json` = `{model, axis:"code_quality", n_records, overall, per_axis, low_confidence, records:[per-record judge_one...]}`. Patch targets: `judge_one`, `aggregate`, `RESULTS`.

- [ ] **Step 1: Write the failing test**

Append to `benchmark/bench/tests/test_judge.py`:

```python
import os
import bench.run_judge as RJ


def test_run_judge_cli_writes_json(tmp_path, monkeypatch):
    recs = tmp_path / "recs.jsonl"
    recs.write_text(json.dumps({"task": "T1", "output": "code1"}) + "\n" +
                    json.dumps({"task": "T2", "output": "code2"}) + "\n")
    monkeypatch.setattr(RJ, "RESULTS", str(tmp_path))
    monkeypatch.setattr(RJ, "judge_one", lambda task, output, reference=None: {
        "per_judge": {}, "median": {"readability": 4}, "judges_used": ["x"], "n_judges": 1})
    rc = RJ.main(["--model", "mymodel", "--records", str(recs)])
    assert rc == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel", "judge.json")))
    assert out["model"] == "mymodel" and out["axis"] == "code_quality"
    assert out["n_records"] == 2 and len(out["records"]) == 2
    assert out["per_axis"]["readability"] == 4.0
```

(Add `import os` and `import bench.run_judge as RJ` to the imports.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_judge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bench.run_judge'`.

- [ ] **Step 3: Implement the CLI**

Create `benchmark/bench/run_judge.py`:

```python
"""CLI: run the mixed-family code-quality judge panel over a model's execution-PASSING
coding outputs.

  # ANTHROPIC_API_KEY set + codex on PATH; records.jsonl = {task, output, reference?} per line:
  cd benchmark && uv run python -m bench.run_judge --model Qwen3.6-27B-UD-MLX-6bit --records passing.jsonl

Writes benchmark/results/<model>/judge.json."""
import argparse
import json
import os

from .judge import judge_one, aggregate

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")


def _read_records(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mixed-family code-quality judge panel.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--records", required=True, help="JSONL of {task, output, reference?}")
    args = ap.parse_args(argv)

    records_in = _read_records(args.records)
    judged = [judge_one(r["task"], r["output"], r.get("reference")) for r in records_in]
    agg = aggregate(judged)
    result = {"model": args.model, "axis": "code_quality", "n_records": agg["n_records"],
              "overall": agg["overall"], "per_axis": agg["per_axis"],
              "low_confidence": agg["low_confidence"], "records": judged}

    print(f"[judge] {args.model} overall={agg['overall']} per_axis={agg['per_axis']} "
          f"n={agg['n_records']} low_confidence={agg['low_confidence']}", flush=True)
    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "judge.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(f"[judge] wrote {os.path.join(out_dir, 'judge.json')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_judge.py -v`
Expected: PASS — all judge tests incl. the CLI.

- [ ] **Step 5: Run the whole suite**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/ -q`
Expected: PASS — full suite green.

- [ ] **Step 6: Commit**

```bash
git add benchmark/bench/run_judge.py benchmark/bench/tests/test_judge.py
git commit -m "bench(judge): run_judge.py CLI -> results/<model>/judge.json"
```

---

## Task 5: README judge-panel section

**Files:**
- Modify: `benchmark/README.md`

**Interfaces:** none (docs only). Delegate to the doc-writer agent.

- [ ] **Step 1: Add the docs**

Add a `## Judge panel (subjective code quality)` section covering: a mixed-family panel (`claude-sonnet-4-6` + `claude-opus-4-8` via the Anthropic API, GPT-5.5 via the `codex` CLI) scores ONLY the 10-axis subjective rubric over execution-PASSING coding outputs (it is NOT a correctness oracle — correctness is execution-gated); blind (no producer identity); per-axis **median** with **per-judge scores reported** and a **low-confidence flag** (fewer than 2 judges, or a large Anthropic-vs-OpenAI split); backends optional + lazy (`uv pip install anthropic` + `ANTHROPIC_API_KEY`; `codex` CLI on PATH) — missing backends are skipped, never crash; standalone `uv run python -m bench.run_judge --model <m> --records passing.jsonl` → `results/<model>/judge.json`. Note the real API/codex calls + JSON adherence are validated at first real run (grade-time, off the measurement box).

- [ ] **Step 2: Verify the entry point exists**

Run: `cd benchmark && uv run python -m bench.run_judge --help`
Expected: usage shows `--model`, `--records`.

- [ ] **Step 3: Commit**

```bash
git add benchmark/README.md
git commit -m "docs(bench): document the mixed-family code-quality judge panel"
```

---

## Running it (execution phase — grade-time, off the measurement box)

```bash
uv pip install anthropic        # + ANTHROPIC_API_KEY for Sonnet/Opus; codex CLI on PATH for GPT-5.5
# passing.jsonl: one {task, output, reference?} per execution-PASSING coding solution
cd benchmark && uv run python -m bench.run_judge --model gemma-4-26B-A4B-it-QAT-MLX-4bit --records passing.jsonl
```

First real run validates the three boundaries the unit tests mock: the live Anthropic call, the exact `codex exec` invocation (confirm the one-shot flag), and live JSON adherence (the parser is defensive, but confirm judges emit the `{"scores": {...}}` shape). Runs on the M2 dev box (no model load) while the M5 measures.

---

## Self-Review

**Spec coverage** (forward-plan Step-1 "mixed-family judge panel: Sonnet + Opus + GPT-5.5/codex, median, per-judge reported"; harness-design §4.6 judge panel, §2/§3q instrument separation):
- Mixed families (Sonnet + Opus + GPT-5.5/codex) → `DEFAULT_JUDGES`. ✓
- Median aggregation + per-judge reported + low-confidence flag → `judge_one`/`aggregate`. ✓
- Blind (no producer identity) → `build_judge_prompt` + its test. ✓
- Judge ≠ correctness oracle; over execution-PASSING outputs only; `reasoning` axis advisory → rubric + docs. ✓
- Optional/lazy/graceful-degrade + never-raise (missing anthropic / no key / codex absent / parse fail) → both backends + `judge_one` + tests. ✓
- Correct Anthropic SDK usage (model IDs, adaptive thinking, no sampling params/`budget_tokens`) → `anthropic_judge` + its param-assertion test. ✓
- Standalone `results/<model>/judge.json` (code_quality axis) → Task 4. ✓

**Placeholder scan:** full code in every step; the run-time-validated boundaries (live Anthropic call, exact `codex exec` flag, JSON adherence) are isolated behind graceful-degrade + flagged in Global Constraints + Running-it.

**Type consistency:** `RUBRIC_AXES: list[str]`; `build_judge_prompt(...) -> (system, user)`; `parse_scores(text) -> {axis:int}|None`; `anthropic_judge(model_id, system, user, max_tokens, client) -> str|None`; `codex_judge(system, user, runner) -> str|None`; `judge_one(...) -> {per_judge, median, judges_used, n_judges}`; `aggregate(records) -> {overall, per_axis, n_records, low_confidence}`; CLI writes that to `judge.json` and patches `RJ.judge_one`/`RJ.aggregate`/`RJ.RESULTS`. Consistent across Tasks 1→4 and the test file.
```

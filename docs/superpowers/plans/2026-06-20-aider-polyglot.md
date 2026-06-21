# Aider Polyglot Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an agentic-edit coding axis by driving the official Aider polyglot benchmark against our mlx-serve OpenAI-compatible endpoint, normalizing its pass-rate into one `results/<model>/aider.json` record.

**Architecture:** Aider's polyglot benchmark (its `benchmark/benchmark.py` harness + the `Aider-AI/polyglot-benchmark` exercises) does its own edit-loop + test execution per exercise. Rather than reimplement aider's edit loop, we **drive its benchmark harness via subprocess** with `OPENAI_API_BASE` pointed at mlx-serve and `--model openai/<served>`, then parse the printed `pass_rate_#`. The adapter is a thin wrapper exactly like the BFCL adapter (`bench/bfcl_adapter.py`): lazy-detect → subprocess-invoke (injectable runner) → parse → normalize, with graceful degradation when aider/its harness isn't present. Standalone probe (like `retrieval.py`/`bfcl_adapter.py`), not the generate→grade jsonl pipeline.

**Tech Stack:** Python 3 stdlib (`subprocess`, `os`, `re`); the official `aider-chat` + its benchmark harness + the polyglot-benchmark exercises (installed/cloned only where it runs). pytest, mocking the subprocess.

## Global Constraints

- **Reuse aider's harness, don't reinvent.** Drive `benchmark/benchmark.py` from a cloned aider repo against our endpoint; do NOT reimplement aider's edit loop, diff application, or test runner.
- **Optional heavy dependency, graceful-degrade + never-raise.** If aider's benchmark harness isn't found (repo path missing) the adapter returns `{skipped: True, acc: None, note}`; a non-zero exit or a raising runner returns `{acc: None, note}`. Never raises (mirror the BFCL `run_bfcl` contract incl. the runner-exception guard).
- **Separate output:** write `results/<model>/aider.json` (aider self-generates; not in the generate→grade jsonl). Consumed by the Step-3 scorecard.
- **Normalize pass-rate to a 0–1 fraction** in `acc` (aider prints `pass_rate_#` as a percentage); record raw `pass_rate_1`/`pass_rate_2`. Headline `acc` = `pass_rate_2` (after aider's allowed second attempt) when present, else `pass_rate_1`.
- **Production endpoint, model-agnostic.** The model under test is whatever mlx-serve serves; aider addresses it as `openai/<served-name>` with `OPENAI_API_BASE=<mlx-serve>/v1` + a dummy `OPENAI_API_KEY`.
- **Run-time-validated boundary (don't over-test):** the real aider invocation, the `openai/<name>` model mapping, docker vs local test execution, and the exact `pass_rate_#` stdout format are validated on the first real run (execution phase). Unit tests cover the pass-rate parsing (canned stdout) + the orchestration arg/env construction + graceful-degrade, mocking `subprocess`.
- **Tests run from `benchmark/`:** `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/`.

---

## File Structure

- `benchmark/bench/aider_adapter.py` — **Create.** `aider_available(aider_repo)`; `parse_pass_rate(stdout) -> dict`; `run_aider(model, exercises_dir, aider_repo, edit_format, num_tests, endpoint, run_name, runner) -> dict`.
- `benchmark/bench/run_aider.py` — **Create.** CLI → `results/<model>/aider.json`.
- `benchmark/bench/tests/test_aider.py` — **Create.** parse_pass_rate (canned); run_aider (mock runner: skip / success / nonzero / raise / normalize); CLI write.
- `benchmark/requirements.txt` — **Modify.** Add `aider-chat` + polyglot-benchmark note (commented, install-where-it-runs).
- `benchmark/README.md` — **Modify.** Aider section (doc-writer).

No change to `run.py`/`benchmarks.py`/`grade.py`.

---

## Task 1: `parse_pass_rate` + `aider_available`

**Files:**
- Create: `benchmark/bench/aider_adapter.py`
- Test: `benchmark/bench/tests/test_aider.py`

**Interfaces:**
- Produces:
  - `aider_available(aider_repo: str) -> bool` — the harness `benchmark/benchmark.py` exists under `aider_repo`.
  - `parse_pass_rate(stdout: str) -> dict` — extract `pass_rate_1`/`pass_rate_2` (floats, percent) from aider benchmark stdout; missing → `None`.

- [ ] **Step 1: Write the failing tests**

Create `benchmark/bench/tests/test_aider.py`:

```python
"""Tests for the Aider polyglot adapter (pass-rate parse, subprocess driving, degrade)."""
import os

import bench.aider_adapter as A


def test_parse_pass_rate_extracts_both():
    stdout = "...\npass_rate_1: 42.5\npass_rate_2: 61.0\nsome other line\n"
    out = A.parse_pass_rate(stdout)
    assert out["pass_rate_1"] == 42.5
    assert out["pass_rate_2"] == 61.0


def test_parse_pass_rate_missing_is_none():
    out = A.parse_pass_rate("no rates printed here")
    assert out["pass_rate_1"] is None and out["pass_rate_2"] is None


def test_aider_available_checks_harness(tmp_path):
    assert A.aider_available(str(tmp_path)) is False
    bdir = tmp_path / "benchmark"
    bdir.mkdir()
    (bdir / "benchmark.py").write_text("# harness")
    assert A.aider_available(str(tmp_path)) is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_aider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bench.aider_adapter'`.

- [ ] **Step 3: Implement**

Create `benchmark/bench/aider_adapter.py`:

```python
"""Adapter that drives the official Aider polyglot benchmark against our mlx-serve
OpenAI-compatible endpoint and normalizes its pass-rate. Aider's harness does its own
edit loop + per-exercise test execution; we only orchestrate + parse. The harness +
exercises install/clone only where this runs (optional); detected lazily, graceful-degrade."""
import os
import re
import subprocess
import sys

AXIS = "agentic_coding"


def aider_available(aider_repo: str) -> bool:
    """The aider benchmark harness lives in the aider REPO (not the pip package)."""
    return bool(aider_repo) and os.path.isfile(os.path.join(aider_repo, "benchmark", "benchmark.py"))


def parse_pass_rate(stdout: str) -> dict:
    """Extract pass_rate_1 / pass_rate_2 (percentages) from aider benchmark stdout."""
    out = {}
    for k in ("pass_rate_1", "pass_rate_2"):
        m = re.search(rf"{k}\s*[:=]\s*([0-9.]+)", stdout or "")
        out[k] = float(m.group(1)) if m else None
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_aider.py -v`
Expected: PASS — all 3 tests.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/aider_adapter.py benchmark/bench/tests/test_aider.py
git commit -m "bench(aider): parse_pass_rate + aider_available (harness detection)"
```

---

## Task 2: `run_aider` (drive the aider benchmark)

**Files:**
- Modify: `benchmark/bench/aider_adapter.py`, `benchmark/requirements.txt`
- Test: `benchmark/bench/tests/test_aider.py`

**Interfaces:**
- Consumes: `aider_available`, `parse_pass_rate`.
- Produces: `run_aider(model, exercises_dir, aider_repo, edit_format="whole", num_tests=None, endpoint="http://localhost:8000/v1", run_name="bake", runner=subprocess.run) -> dict` — sets `OPENAI_API_BASE`/`OPENAI_API_KEY`, subprocess-runs `<aider_repo>/benchmark/benchmark.py <run_name> --model openai/<model> --edit-format <fmt> --threads 1 --exercises-dir <dir> --new [--num-tests N]` via `runner`, parses `pass_rate_#` from stdout, normalizes. Returns `{model, axis, tool:"aider_polyglot", edit_format, pass_rate_1, pass_rate_2, acc, skipped, note?}`. Graceful-degrade: harness absent → skipped; runner raises → note; non-zero exit → note.

- [ ] **Step 1: Write the failing tests**

Append to `benchmark/bench/tests/test_aider.py`:

```python
import types


def test_run_aider_skips_when_harness_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: False)
    out = A.run_aider("m", exercises_dir=str(tmp_path), aider_repo=str(tmp_path))
    assert out["skipped"] is True and out["acc"] is None and "note" in out
    assert out["axis"] == "agentic_coding" and out["tool"] == "aider_polyglot"


def test_run_aider_success_parses_and_normalizes(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)
    captured = {}

    def fake_runner(cmd, **kw):
        captured["cmd"] = cmd
        captured["env"] = kw.get("env", {})
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_1: 40.0\npass_rate_2: 55.0\n", stderr="")

    out = A.run_aider("Qwen3.6-27B-UD-MLX-6bit", exercises_dir="/ex", aider_repo="/aider",
                      num_tests=3, runner=fake_runner)
    assert out["pass_rate_2"] == 55.0
    assert out["acc"] == 0.55                      # pass_rate_2 normalized
    assert out["skipped"] is False
    assert "openai/Qwen3.6-27B-UD-MLX-6bit" in captured["cmd"]
    assert "--num-tests" in captured["cmd"] and "3" in captured["cmd"]
    assert captured["env"]["OPENAI_API_BASE"].endswith("/v1")


def test_run_aider_falls_back_to_rate1(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout="pass_rate_1: 30.0\n", stderr="")

    out = A.run_aider("m", "/ex", "/aider", runner=fake_runner)
    assert out["acc"] == 0.30                      # pass_rate_2 absent -> rate_1


def test_run_aider_nonzero_exit_degrades(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def fake_runner(cmd, **kw):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="boom")

    out = A.run_aider("m", "/ex", "/aider", runner=fake_runner)
    assert out["acc"] is None and "note" in out and out["skipped"] is False


def test_run_aider_runner_raises_degrades(monkeypatch):
    monkeypatch.setattr(A, "aider_available", lambda repo: True)

    def boom(cmd, **kw):
        raise FileNotFoundError("python gone")

    out = A.run_aider("m", "/ex", "/aider", runner=boom)
    assert out["acc"] is None and "raised" in out["note"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_aider.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'run_aider'`.

- [ ] **Step 3: Implement `run_aider`**

Append to `benchmark/bench/aider_adapter.py`:

```python
def run_aider(model, exercises_dir, aider_repo, edit_format="whole", num_tests=None,
              endpoint="http://localhost:8000/v1", run_name="bake",
              runner=subprocess.run) -> dict:
    """Drive the aider polyglot benchmark against the local mlx-serve endpoint and normalize
    the pass-rate. `runner` is injectable for tests. Never raises; graceful-degrade."""
    base = {"model": model, "axis": AXIS, "tool": "aider_polyglot", "edit_format": edit_format}
    if not aider_available(aider_repo):
        return {**base, "acc": None, "skipped": True,
                "note": f"aider harness not found under {aider_repo!r}; "
                        f"clone Aider-AI/aider + polyglot-benchmark (see README)"}
    env = {**os.environ, "OPENAI_API_BASE": endpoint, "OPENAI_API_KEY": "sk-local"}
    cmd = [sys.executable, os.path.join(aider_repo, "benchmark", "benchmark.py"), run_name,
           "--model", f"openai/{model}", "--edit-format", edit_format,
           "--threads", "1", "--exercises-dir", exercises_dir, "--new"]
    if num_tests is not None:
        cmd += ["--num-tests", str(num_tests)]
    try:
        proc = runner(cmd, env=env, capture_output=True, text=True)
    except Exception as e:  # noqa: BLE001 — harness/python launch failure; degrade
        return {**base, "acc": None, "skipped": False,
                "note": f"aider runner raised: {type(e).__name__}: {str(e)[:120]}"}
    rc = getattr(proc, "returncode", 1)
    if rc != 0:
        return {**base, "acc": None, "skipped": False,
                "note": f"aider benchmark failed rc={rc}: {(getattr(proc, 'stderr', '') or '')[:160]}"}
    rates = parse_pass_rate(getattr(proc, "stdout", "") or "")
    pr = rates.get("pass_rate_2")
    if pr is None:
        pr = rates.get("pass_rate_1")
    if pr is None:  # ran (rc=0) but no pass_rate parsed -> likely an output-format mismatch
        return {**base, **rates, "acc": None, "skipped": False,
                "note": "aider ran (rc=0) but no pass_rate_# parsed from stdout — check aider output format"}
    acc = pr / 100.0 if pr > 1.0 else pr   # aider prints percentages (0-100) -> 0-1 fraction
    return {**base, **rates, "acc": acc, "skipped": False}
```

Append to `benchmark/requirements.txt`:

```
# Aider polyglot (agentic edit) — drives aider's OWN benchmark harness against the
# mlx-serve endpoint (bench/aider_adapter.py). Optional; install where it runs:
#   uv pip install aider-chat
#   git clone https://github.com/Aider-AI/aider                 # provides benchmark/benchmark.py
#   git clone https://github.com/Aider-AI/polyglot-benchmark    # the exercises (--exercises-dir)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_aider.py -v`
Expected: PASS — degrade, success+normalize, rate1-fallback, nonzero, raise.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/aider_adapter.py benchmark/requirements.txt benchmark/bench/tests/test_aider.py
git commit -m "bench(aider): run_aider drives aider polyglot benchmark, graceful-degrade"
```

---

## Task 3: `run_aider.py` CLI

**Files:**
- Create: `benchmark/bench/run_aider.py`
- Test: `benchmark/bench/tests/test_aider.py`

**Interfaces:**
- Consumes: `aider_adapter.run_aider`.
- Produces: `main(argv=None) -> int` — args `--model` (required), `--exercises-dir` (required), `--aider-repo` (required), `--edit-format` (default `whole`), `--num-tests`, `--endpoint` (default `http://localhost:8000/v1`), `--run-name` (default `bake`); calls `run_aider`, writes `results/<model>/aider.json`, prints summary, returns 0. Patch targets: `run_aider`, `RESULTS`.

- [ ] **Step 1: Write the failing test**

Append to `benchmark/bench/tests/test_aider.py`:

```python
import json
import bench.run_aider as RA


def test_run_aider_cli_writes_json(tmp_path, monkeypatch):
    monkeypatch.setattr(RA, "RESULTS", str(tmp_path))
    monkeypatch.setattr(RA, "run_aider", lambda **kw: {
        "model": kw["model"], "axis": "agentic_coding", "tool": "aider_polyglot",
        "edit_format": "whole", "pass_rate_1": 40.0, "pass_rate_2": 55.0, "acc": 0.55,
        "skipped": False})
    rc = RA.main(["--model", "mymodel", "--exercises-dir", "/ex", "--aider-repo", "/aider"])
    assert rc == 0
    out = json.load(open(os.path.join(tmp_path, "mymodel", "aider.json")))
    assert out["model"] == "mymodel" and out["acc"] == 0.55 and out["tool"] == "aider_polyglot"
```

(Add `import json` and `import bench.run_aider as RA` to the imports.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_aider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bench.run_aider'`.

- [ ] **Step 3: Implement the CLI**

Create `benchmark/bench/run_aider.py`:

```python
"""CLI: run the Aider polyglot benchmark against the live mlx-serve endpoint.

  # mlx-serve serving <model> at :8000; aider + polyglot-benchmark cloned:
  cd benchmark && uv run python -m bench.run_aider --model Qwen3.6-27B-UD-MLX-6bit \
      --aider-repo ~/aider --exercises-dir ~/polyglot-benchmark

Writes benchmark/results/<model>/aider.json."""
import argparse
import json
import os

from .aider_adapter import run_aider

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Aider polyglot agentic-edit benchmark.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--exercises-dir", required=True)
    ap.add_argument("--aider-repo", required=True)
    ap.add_argument("--edit-format", default="whole")
    ap.add_argument("--num-tests", type=int, default=None)
    ap.add_argument("--endpoint", default="http://localhost:8000/v1")
    ap.add_argument("--run-name", default="bake")
    args = ap.parse_args(argv)

    result = run_aider(model=args.model, exercises_dir=args.exercises_dir,
                       aider_repo=args.aider_repo, edit_format=args.edit_format,
                       num_tests=args.num_tests, endpoint=args.endpoint, run_name=args.run_name)
    if result.get("skipped"):
        print(f"[aider] SKIPPED: {result.get('note')}", flush=True)
    elif result.get("acc") is None:
        print(f"[aider] NO SCORE: {result.get('note')}", flush=True)
    else:
        print(f"[aider] {args.model} acc={result.get('acc')} "
              f"pass_rate_1={result.get('pass_rate_1')} pass_rate_2={result.get('pass_rate_2')}", flush=True)

    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "aider.json"), "w") as f:
        json.dump(result, f, indent=2)
    print(f"[aider] wrote {os.path.join(out_dir, 'aider.json')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/test_aider.py -v`
Expected: PASS — all aider tests.

- [ ] **Step 5: Run the whole suite**

Run: `cd benchmark && uv run --with pytest --with psutil python -m pytest bench/tests/ -q`
Expected: PASS — full suite green.

- [ ] **Step 6: Commit**

```bash
git add benchmark/bench/run_aider.py benchmark/bench/tests/test_aider.py
git commit -m "bench(aider): run_aider.py CLI -> results/<model>/aider.json"
```

---

## Task 4: README Aider section

**Files:**
- Modify: `benchmark/README.md`

**Interfaces:** none (docs only). Delegate to the doc-writer agent.

- [ ] **Step 1: Add the docs**

Add a `### Aider polyglot (agentic edit)` subsection under `## Benchmarks` conveying: drives aider's OWN polyglot benchmark harness (optional — `pip install aider-chat`, clone `Aider-AI/aider` for `benchmark/benchmark.py` + `Aider-AI/polyglot-benchmark` for the exercises) against the running mlx-serve endpoint (`OPENAI_API_BASE`, `--model openai/<served>`, `--edit-format whole`); standalone probe (`uv run python -m bench.run_aider --model <m> --aider-repo <dir> --exercises-dir <dir>`) → `results/<model>/aider.json` with `pass_rate_1`/`pass_rate_2` and a count… (fraction) `acc` = pass_rate_2; if the harness isn't found it records `skipped: true`. Each exercise runs in aider's own sandbox/docker; the `openai/<name>` mapping is resolved at first real run.

````markdown
## Aider polyglot (agentic edit)

`bench/run_aider.py` measures agentic edit-via-instruction by driving Aider's own polyglot
benchmark harness (optional). Install where it runs: `pip install aider-chat`, then clone the
aider repo (for `benchmark/benchmark.py`) and the exercises:

```bash
git clone https://github.com/Aider-AI/aider
git clone https://github.com/Aider-AI/polyglot-benchmark
cd benchmark && uv run python -m bench.run_aider --model Qwen3.6-27B-UD-MLX-6bit \
    --aider-repo ../aider --exercises-dir ../polyglot-benchmark
```

It points aider at the mlx-serve endpoint (`OPENAI_API_BASE`, `--model openai/<served>`,
`--edit-format whole`) and parses aider's `pass_rate_#`. Writes `results/<model>/aider.json`
with `pass_rate_1`/`pass_rate_2` and a 0–1 `acc` (= pass_rate_2, aider's second-attempt rate).
If the harness isn't found it records `skipped: true` + a note. Aider runs each exercise in its
own sandbox; the `openai/<name>` handler mapping is confirmed on the first real run.
````

- [ ] **Step 2: Verify the entry point exists**

Run: `cd benchmark && uv run python -m bench.run_aider --help`
Expected: usage shows `--model`, `--exercises-dir`, `--aider-repo`, `--edit-format`, `--num-tests`, `--endpoint`, `--run-name`.

- [ ] **Step 3: Commit**

```bash
git add benchmark/README.md
git commit -m "docs(bench): document the Aider polyglot adapter"
```

---

## Self-Review

**Spec coverage** (forward-plan Step-1 "Coding (agentic, in-loop): Aider polyglot"; harness-design §4.4 `aider_polyglot.py`, §6 "Use Aider polyglot"):
- Aider agentic-edit axis via the official harness → Tasks 1–3. ✓
- Reuse, not reinvent (drive aider's benchmark.py; no reimplemented edit loop) → Task 2. ✓
- Optional/lazy/graceful-degrade + never-raise (skip/nonzero/raise paths) → `run_aider` + tests. ✓
- Separate `results/<model>/aider.json` → Task 3. ✓
- pass_rate normalized to a fraction; raw rates recorded → Task 2. ✓

**Placeholder scan:** full code in every step; run-time-validated boundaries (real aider invocation, `openai/<name>` mapping, docker/local execution, exact `pass_rate_#` format) isolated behind graceful-degrade + flagged.

**Type consistency:** `aider_available(repo)->bool`, `parse_pass_rate(stdout)->{pass_rate_1,pass_rate_2}`, `run_aider(...)->{model,axis,tool,edit_format,pass_rate_1,pass_rate_2,acc,skipped,note?}`, CLI writes that to `aider.json`. CLI patches `RA.run_aider`/`RA.RESULTS` (module-level). Consistent across Tasks 1→2→3 and the test file. Mirrors the BFCL adapter exactly.

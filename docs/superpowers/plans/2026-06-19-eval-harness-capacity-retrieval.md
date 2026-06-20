# Eval Harness — Capacity + Retrieval MVP (Phase 0a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the harness spine + the capacity/retrieval axis so we can produce the single highest-value measurement — does `Qwen3.6-27B-UD-MLX-6bit` actually fit 256K within the 46GB gate, and how deep does retrieval hold.

**Architecture:** A thin framework-agnostic driver wraps the existing stdlib `client.probe()` (MLX-serve today; the `Driver` protocol is the seam llama.cpp slots into later). A background `MemorySampler` records peak memory on the box under test. A `capacity_ladder` grows the same context in 32K steps {160K→256K}, captures peak each step, scores a multi-needle retrieval query, and stops at the 46GB gate. A `scorecard` normalizes the per-L records into one comparable JSON. The harness runs **on the box under test** (localhost:8000), matching how `needle_256k.py`/`validate_256k.py` already work.

**Tech Stack:** Python 3.12, stdlib HTTP (urllib, matching the existing harness), `psutil` (with a `resource` fallback, as in `mem_decompose.py`), `pytest` for the harness's own unit tests. Drives the mlx-serve fork over HTTP.

**Scope note:** This is Phase **0a** of the eval-harness spec (`docs/superpowers/specs/2026-06-19-local-256k-eval-harness-design.md`). It implements axes **1 (capacity)** and **2a (retrieval)** only. The reasoning axis (2b: RULER/NoLiMa/LongCodeBench), agentic-coding axis (3: BFCL/Aider/SWE/IFEval), execution-gated correctness, and the judge panel are **deliberately out of scope** — they are Phase 0b/0c plans built on this spine.

## Global Constraints

- **Capacity gate:** model footprint peak ≤ **46GB** (usable profile); also report total system-used peak. Copied from spec §7.
- **Retrieval/capacity L-grid:** `{160_000, 192_000, 224_000, 256_000}` tokens, incremental 32K fill, RSS captured at each step; stop the moment footprint > 46GB. Spec §7.
- **Effective-length threshold:** retrieval accuracy ≥ **0.85**. Spec §7.
- **Runs on the box under test:** harness and server co-located; `MLX_SERVE_BASE` defaults to `http://localhost:8000` (existing `client.py`). M5 reached via `ssh $REMOTE_HOST` (repos under `~/Documents/ws/`).
- **One model at a time:** never load two big models concurrently; unload/`preload` deliberately (project RAM constraint).
- **Edit parent forks, not submodules:** this plan touches only `benchmark/` in the stack repo; no mlx-vlm/mlx-serve changes. If a server change is ever needed, it goes in the `../mlx-vlm` / `../mlx-serve` parent forks, not `src/*`.
- **Results location:** `benchmark/results/<model>/capacity_retrieval.json` (+ raw `benchmark/results/<model>/capacity_ladder.jsonl`), matching the existing `benchmark/results/` convention.
- **Module path:** new code lives in `benchmark/bench/` (the existing harness package); tests in `benchmark/bench/tests/`.

---

## File Structure

- `benchmark/bench/client.py` — **modify**: add `raw_timings` passthrough to `probe()` (backward-compatible) so the driver can derive prefill metrics.
- `benchmark/bench/driver.py` — **create**: `Driver` protocol + `MlxServeDriver` (wraps `client`), normalizes one completion into a `Completion` dict with derived `prefill_s`/`prefill_tps`.
- `benchmark/bench/instrument.py` — **create**: `MemorySampler` (background thread; system-used + optional per-PID RSS peak) and the `PerfRecord` dataclass.
- `benchmark/bench/retrieval.py` — **create**: multi-needle context builder (one unique code per depth, single query) + `score()`.
- `benchmark/bench/capacity_ladder.py` — **create**: the incremental-fill ladder; ties driver + sampler + retrieval together; enforces the 46GB gate.
- `benchmark/bench/scorecard.py` — **create**: aggregate ladder records → the capacity/retrieval scorecard.
- `benchmark/bench/run_capacity.py` — **create**: CLI entrypoint; writes results.
- `benchmark/bench/tests/` — **create**: `test_driver.py`, `test_instrument.py`, `test_retrieval.py`, `test_capacity_ladder.py`, `test_scorecard.py`.
- `benchmark/requirements.txt` — **modify**: add `pytest` and `psutil`.

---

### Task 1: Driver (framework-agnostic completion seam)

**Files:**
- Modify: `benchmark/bench/client.py` (the `probe()` return dict)
- Create: `benchmark/bench/driver.py`
- Create: `benchmark/bench/tests/test_driver.py`
- Modify: `benchmark/requirements.txt`

**Interfaces:**
- Consumes: `client.probe(model, messages, params, timeout)`, `client.preload(model, timeout)` (existing).
- Produces: `MlxServeDriver().complete(model, messages, params, timeout) -> dict` with keys `content, reasoning, prompt_tokens, completion_tokens, decode_tps, prefill_tps, prefill_s, peak_mem_gb, wall_s, finish_reason`. `MlxServeDriver().preload(model, timeout) -> float`. The `Driver` protocol has exactly `complete(...)` and `preload(...)`.

- [ ] **Step 1: Add `pytest` and `psutil` to requirements**

Append to `benchmark/requirements.txt`:

```
pytest>=8
psutil>=5.9
```

- [ ] **Step 2: Write the failing driver test**

Create `benchmark/bench/tests/test_driver.py`:

```python
import json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from bench.driver import MlxServeDriver

CANNED = {
    "choices": [{"message": {"content": "ANSWER", "reasoning": ""}, "finish_reason": "stop"}],
    "usage": {"prompt_tokens": 1000, "completion_tokens": 10},
    "timings": {"predicted_per_second": 20.0, "predicted_ms": 500.0, "peak_memory": 40.4, "prompt_n": 1000},
}

class _H(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps(CANNED).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass

def test_complete_parses_and_derives_prefill(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("MLX_SERVE_BASE", f"http://127.0.0.1:{srv.server_address[1]}")
    import importlib, bench.client; importlib.reload(bench.client)
    import bench.driver; importlib.reload(bench.driver)
    d = bench.driver.MlxServeDriver()
    out = d.complete("m", [{"role": "user", "content": "hi"}], {"max_tokens": 16})
    srv.shutdown()
    assert out["content"] == "ANSWER"
    assert out["prompt_tokens"] == 1000
    assert out["decode_tps"] == 20.0
    # prefill_s = wall - predicted_ms/1000 ; prefill_tps = prompt_tokens / prefill_s
    assert out["prefill_s"] > 0
    assert out["prefill_tps"] > 0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd benchmark && python -m pytest bench/tests/test_driver.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench.driver'`.

- [ ] **Step 4: Add `raw_timings` to `client.probe()`**

In `benchmark/bench/client.py`, in the dict returned by `probe()`, add one key (leave all existing keys unchanged):

```python
        "wall_s": round(wall, 1),
        "raw_timings": tm,
```

- [ ] **Step 5: Implement `driver.py`**

Create `benchmark/bench/driver.py`:

```python
"""Framework-agnostic completion driver. MVP backend: the mlx-serve router via the
existing stdlib client. The Driver protocol is the seam llama.cpp slots into later."""
from typing import Protocol
from . import client


class Driver(Protocol):
    def preload(self, model: str, timeout: float = 900) -> float: ...
    def complete(self, model: str, messages: list, params: dict,
                 timeout: float = 3600) -> dict: ...


class MlxServeDriver:
    """Wraps benchmark.bench.client. Derives prefill_s / prefill_tps from the server
    timings the same way needle_256k.py does (wall minus server-reported decode time)."""

    def preload(self, model: str, timeout: float = 900) -> float:
        return client.preload(model, timeout=timeout)

    def complete(self, model: str, messages: list, params: dict,
                 timeout: float = 3600) -> dict:
        r = client.probe(model, messages, params, timeout=timeout)
        tm = r.get("raw_timings") or {}
        wall = r.get("wall_s") or 0.0
        pred_ms = tm.get("predicted_ms") or 0.0
        pt = r.get("prompt_tokens")
        prefill_s = max(wall - pred_ms / 1000, 0.01)
        return {
            "content": r.get("content", ""),
            "reasoning": r.get("reasoning", ""),
            "prompt_tokens": pt,
            "completion_tokens": r.get("completion_tokens"),
            "decode_tps": r.get("decode_tps"),
            "prefill_s": round(prefill_s, 2),
            "prefill_tps": round(pt / prefill_s) if pt else None,
            "peak_mem_gb": r.get("peak_mem_gb"),
            "wall_s": wall,
            "finish_reason": r.get("finish_reason"),
        }
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd benchmark && python -m pytest bench/tests/test_driver.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add benchmark/bench/driver.py benchmark/bench/client.py benchmark/bench/tests/test_driver.py benchmark/requirements.txt
git commit -m "feat(bench): framework-agnostic completion driver (MLX-serve) + prefill derivation"
```

---

### Task 2: Memory instrumentation

**Files:**
- Create: `benchmark/bench/instrument.py`
- Create: `benchmark/bench/tests/test_instrument.py`

**Interfaces:**
- Produces: `MemorySampler(pid=None, interval=0.2)` as a context manager; after exit exposes `.peak_rss_gb` (float; 0.0 if no pid) and `.model_footprint_gb` (float = peak system-used minus the baseline captured at construction). `PerfRecord` dataclass with fields `ctx:int, peak_rss_gb:float, model_footprint_gb:float, system_peak_gb:float, server_peak_gb:float|None, prefill_s:float|None, prefill_tps:float|None, decode_tps:float|None, prompt_tokens:int|None, bottleneck:str`.
- Module-level helpers `system_used_gb() -> float` and `rss_gb(pid) -> float` (monkeypatchable in tests).

- [ ] **Step 1: Write the failing test**

Create `benchmark/bench/tests/test_instrument.py`:

```python
import bench.instrument as I

def test_sampler_tracks_footprint(monkeypatch):
    seq = iter([10.0, 10.0, 55.0, 30.0])  # baseline=10, peak=55
    monkeypatch.setattr(I, "system_used_gb", lambda: next(seq))
    s = I.MemorySampler(interval=0.001)
    with s:
        import time; time.sleep(0.02)
    assert s.model_footprint_gb == 45.0   # 55 - 10 baseline
    assert s.system_peak_gb == 55.0

def test_perfrecord_defaults():
    r = I.PerfRecord(ctx=256000)
    assert r.ctx == 256000 and r.bottleneck == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd benchmark && python -m pytest bench/tests/test_instrument.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench.instrument'`.

- [ ] **Step 3: Implement `instrument.py`**

Create `benchmark/bench/instrument.py`:

```python
"""Memory + perf instrumentation for a benchmark run on the box under test.
MemorySampler polls system memory (and optionally one process's RSS) in a thread.
Mirrors mem_decompose.py's psutil-with-resource-fallback approach."""
import os
import threading
from dataclasses import dataclass

GB = 1e9


def system_used_gb() -> float:
    import psutil
    vm = psutil.virtual_memory()
    return (vm.total - vm.available) / GB


def rss_gb(pid: int) -> float:
    try:
        import psutil
        return psutil.Process(pid).memory_info().rss / GB
    except Exception:
        import resource
        m = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return (m if m > 1e9 else m * 1024) / GB


class MemorySampler:
    """Captures peak system-used and (optionally) one PID's peak RSS while active.
    model_footprint_gb = peak system-used minus the baseline at construction, i.e.
    what the model+KV cost on top of whatever else was already running."""

    def __init__(self, pid: int | None = None, interval: float = 0.2):
        self.pid = pid
        self.interval = interval
        self._base_sys = system_used_gb()
        self._peak_sys = self._base_sys
        self._peak_rss = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._peak_sys = max(self._peak_sys, system_used_gb())
                if self.pid:
                    self._peak_rss = max(self._peak_rss, rss_gb(self.pid))
            except Exception:
                pass
            self._stop.wait(self.interval)

    def __enter__(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    @property
    def system_peak_gb(self) -> float:
        return round(self._peak_sys, 2)

    @property
    def model_footprint_gb(self) -> float:
        return round(self._peak_sys - self._base_sys, 2)

    @property
    def peak_rss_gb(self) -> float:
        return round(self._peak_rss, 2)


@dataclass
class PerfRecord:
    ctx: int
    peak_rss_gb: float = 0.0
    model_footprint_gb: float = 0.0
    system_peak_gb: float = 0.0
    server_peak_gb: float | None = None
    prefill_s: float | None = None
    prefill_tps: float | None = None
    decode_tps: float | None = None
    prompt_tokens: int | None = None
    bottleneck: str = "unknown"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd benchmark && python -m pytest bench/tests/test_instrument.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/instrument.py benchmark/bench/tests/test_instrument.py
git commit -m "feat(bench): MemorySampler + PerfRecord instrumentation"
```

---

### Task 3: Multi-needle retrieval probe

**Files:**
- Create: `benchmark/bench/retrieval.py`
- Create: `benchmark/bench/tests/test_retrieval.py`

**Interfaces:**
- Produces: `build_context(target_tokens: int, chars_per_token: float, depths=DEPTHS) -> tuple[str, list[str]]` returning `(context, needles)` with one unique code placed at each depth; `make_question(needles) -> str`; `score(response_text: str, needles: list[str]) -> float` (fraction of needles present). `DEPTHS = (0.1, 0.3, 0.5, 0.7, 0.9)`.

- [ ] **Step 1: Write the failing test**

Create `benchmark/bench/tests/test_retrieval.py`:

```python
from bench.retrieval import build_context, score, make_question, DEPTHS

def test_build_places_all_needles_in_order():
    ctx, needles = build_context(2000, chars_per_token=4.0)
    assert len(needles) == len(DEPTHS)
    assert len(set(needles)) == len(needles)          # all unique
    positions = [ctx.find(n) for n in needles]
    assert all(p >= 0 for p in positions)             # all present
    assert positions == sorted(positions)             # placed by ascending depth

def test_score_is_fraction_found():
    _, needles = build_context(2000, 4.0)
    assert score(" ".join(needles), needles) == 1.0
    assert score(needles[0], needles) == 1.0 / len(needles)
    assert score("nothing here", needles) == 0.0

def test_question_mentions_count():
    _, needles = build_context(2000, 4.0)
    assert str(len(needles)) in make_question(needles)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd benchmark && python -m pytest bench/tests/test_retrieval.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench.retrieval'`.

- [ ] **Step 3: Implement `retrieval.py`**

Create `benchmark/bench/retrieval.py`:

```python
"""Multi-needle retrieval probe: one unique code per depth, a single query asking
for all of them (multi-key NIAH). Generalizes needle_256k.py so one prefill scores
retrieval across the whole context. Score = fraction of codes returned."""
FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "
DEPTHS = (0.1, 0.3, 0.5, 0.7, 0.9)


def _needle(i: int) -> str:
    # Non-natural tokens that won't appear in filler; distinct per depth.
    return f"XKRZ{i}{'ABCDEFGHJK'[i]}7Q"


def build_context(target_tokens: int, chars_per_token: float,
                  depths=DEPTHS) -> tuple[str, list[str]]:
    target_chars = int(target_tokens * chars_per_token)
    filler = FILLER * (target_chars // len(FILLER) + 2)
    needles = [_needle(i) for i in range(len(depths))]
    # Insert from deepest to shallowest so earlier inserts don't shift later offsets.
    chars = list(filler[:target_chars])
    for i in sorted(range(len(depths)), key=lambda k: depths[k], reverse=True):
        pos = min(int(target_chars * depths[i]), len(chars) - 1)
        sentence = f" The secret code number {i} is {needles[i]}. "
        chars[pos:pos] = list(sentence)
    return "".join(chars), needles


def make_question(needles: list[str]) -> str:
    return (f"The document above contains {len(needles)} secret codes, each stated once. "
            f"List all {len(needles)} codes, separated by commas. Output only the codes.")


def score(response_text: str, needles: list[str]) -> float:
    if not needles:
        return 0.0
    return sum(1 for n in needles if n in (response_text or "")) / len(needles)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd benchmark && python -m pytest bench/tests/test_retrieval.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/retrieval.py benchmark/bench/tests/test_retrieval.py
git commit -m "feat(bench): multi-needle retrieval probe (multi-key NIAH, single query)"
```

---

### Task 4: Capacity ladder

**Files:**
- Create: `benchmark/bench/capacity_ladder.py`
- Create: `benchmark/bench/tests/test_capacity_ladder.py`

**Interfaces:**
- Consumes: a `Driver` (Task 1) with `.complete(...)`; `MemorySampler`/`PerfRecord` (Task 2); `build_context`/`make_question`/`score` (Task 3).
- Produces: `run_ladder(driver, model, chars_per_token, grid=DEFAULT_GRID, gate_gb=46.0, sampler_factory=MemorySampler) -> list[dict]`. Each dict = a `PerfRecord` (as `dataclasses.asdict`) plus `retrieval_acc: float` and `fits: bool`. The ladder stops after the first L whose `model_footprint_gb > gate_gb` (that L is still recorded, marked `fits=False`). `DEFAULT_GRID = (160_000, 192_000, 224_000, 256_000)`.

- [ ] **Step 1: Write the failing test**

Create `benchmark/bench/tests/test_capacity_ladder.py`:

```python
import bench.capacity_ladder as L

class FakeDriver:
    def __init__(self, footprints):  # footprint per call, GB
        self.footprints = list(footprints); self.calls = 0
    def complete(self, model, messages, params, timeout=3600):
        self.calls += 1
        return {"content": "XKRZ0A7Q, XKRZ1B7Q, XKRZ2C7Q, XKRZ3D7Q, XKRZ4E7Q",
                "prompt_tokens": 1000, "prefill_s": 5.0, "prefill_tps": 200,
                "decode_tps": 9.5, "peak_mem_gb": 40.0}

class FakeSampler:
    """sampler_factory returns one of these per L; footprint scripted via a shared list."""
    seq = None
    def __init__(self, **kw): self.fp = next(FakeSampler.seq)
    def __enter__(self): return self
    def __exit__(self, *a): pass
    model_footprint_gb = 0.0
    system_peak_gb = 0.0
    peak_rss_gb = 0.0
    def __getattribute__(self, k):
        if k == "model_footprint_gb": return object.__getattribute__(self, "fp")
        return object.__getattribute__(self, k)

def test_ladder_stops_at_gate(monkeypatch):
    FakeSampler.seq = iter([30.0, 38.0, 48.0, 99.0])  # 3rd L (224K) trips 46GB gate
    recs = L.run_ladder(FakeDriver([]), "m", chars_per_token=4.0,
                        sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000, 224000]  # stopped after the fail
    assert recs[0]["fits"] and recs[1]["fits"]
    assert recs[2]["fits"] is False
    assert recs[0]["retrieval_acc"] == 1.0  # all 5 needles echoed by FakeDriver

def test_ladder_all_fit(monkeypatch):
    FakeSampler.seq = iter([30.0, 33.0, 36.0, 40.0])
    recs = L.run_ladder(FakeDriver([]), "m", chars_per_token=4.0,
                        sampler_factory=FakeSampler)
    assert [r["ctx"] for r in recs] == [160000, 192000, 224000, 256000]
    assert all(r["fits"] for r in recs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd benchmark && python -m pytest bench/tests/test_capacity_ladder.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench.capacity_ladder'`.

- [ ] **Step 3: Implement `capacity_ladder.py`**

Create `benchmark/bench/capacity_ladder.py`:

```python
"""Incremental-fill capacity + retrieval ladder. Grows the context in 32K steps,
captures peak memory each step, scores multi-needle retrieval, and stops at the
46GB footprint gate. One completion per rung (one prefill), so cost is bounded."""
from dataclasses import asdict
from .instrument import MemorySampler, PerfRecord
from .retrieval import build_context, make_question, score

DEFAULT_GRID = (160_000, 192_000, 224_000, 256_000)
GATE_GB = 46.0


def run_ladder(driver, model: str, chars_per_token: float,
               grid=DEFAULT_GRID, gate_gb: float = GATE_GB,
               sampler_factory=MemorySampler, max_tokens: int = 256) -> list[dict]:
    records: list[dict] = []
    for ctx in grid:
        context, needles = build_context(ctx, chars_per_token)
        messages = [{"role": "user", "content": context + "\n\n" + make_question(needles)}]
        with sampler_factory() as sampler:
            out = driver.complete(model, messages,
                                  {"max_tokens": max_tokens, "temperature": 0.0})
        rec = PerfRecord(
            ctx=ctx,
            model_footprint_gb=sampler.model_footprint_gb,
            system_peak_gb=sampler.system_peak_gb,
            peak_rss_gb=sampler.peak_rss_gb,
            server_peak_gb=out.get("peak_mem_gb"),
            prefill_s=out.get("prefill_s"),
            prefill_tps=out.get("prefill_tps"),
            decode_tps=out.get("decode_tps"),
            prompt_tokens=out.get("prompt_tokens"),
        )
        fits = rec.model_footprint_gb <= gate_gb
        row = {**asdict(rec),
               "retrieval_acc": score(out.get("content", ""), needles),
               "fits": fits}
        records.append(row)
        if not fits:
            break  # stop the ladder once the footprint gate is tripped
    return records
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd benchmark && python -m pytest bench/tests/test_capacity_ladder.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/capacity_ladder.py benchmark/bench/tests/test_capacity_ladder.py
git commit -m "feat(bench): incremental-fill capacity+retrieval ladder with 46GB gate"
```

---

### Task 5: Scorecard

**Files:**
- Create: `benchmark/bench/scorecard.py`
- Create: `benchmark/bench/tests/test_scorecard.py`

**Interfaces:**
- Consumes: the `list[dict]` from `run_ladder`.
- Produces: `capacity_retrieval_scorecard(model: str, records: list[dict], gate_gb=46.0, retrieval_threshold=0.85) -> dict` with keys `model, axis="capacity_retrieval", gate_gb, records, max_fitting_ctx (int|None), capacity_gate_pass (bool, True iff 256K fits), retrieval_effective_ctx (int|None = largest fitting ctx with retrieval_acc >= threshold)`.

- [ ] **Step 1: Write the failing test**

Create `benchmark/bench/tests/test_scorecard.py`:

```python
from bench.scorecard import capacity_retrieval_scorecard

def _rec(ctx, fp, acc, fits): 
    return {"ctx": ctx, "model_footprint_gb": fp, "retrieval_acc": acc, "fits": fits}

def test_full_pass():
    recs = [_rec(160000, 30, 1.0, True), _rec(192000, 33, 1.0, True),
            _rec(224000, 36, 0.8, True), _rec(256000, 40, 0.9, True)]
    sc = capacity_retrieval_scorecard("m", recs)
    assert sc["capacity_gate_pass"] is True
    assert sc["max_fitting_ctx"] == 256000
    # 224K had acc 0.8 (<0.85) but 256K is 0.9 -> effective is the largest passing
    assert sc["retrieval_effective_ctx"] == 256000

def test_gate_fail_midway():
    recs = [_rec(160000, 30, 1.0, True), _rec(192000, 48, 0.0, False)]
    sc = capacity_retrieval_scorecard("m", recs)
    assert sc["capacity_gate_pass"] is False
    assert sc["max_fitting_ctx"] == 160000
    assert sc["retrieval_effective_ctx"] == 160000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd benchmark && python -m pytest bench/tests/test_scorecard.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench.scorecard'`.

- [ ] **Step 3: Implement `scorecard.py`**

Create `benchmark/bench/scorecard.py`:

```python
"""Aggregate capacity-ladder records into one comparable scorecard (axes 1 + 2a)."""

GATE_GB = 46.0
RETRIEVAL_THRESHOLD = 0.85


def capacity_retrieval_scorecard(model: str, records: list[dict],
                                 gate_gb: float = GATE_GB,
                                 retrieval_threshold: float = RETRIEVAL_THRESHOLD) -> dict:
    fitting = [r for r in records if r.get("fits")]
    max_fitting = max((r["ctx"] for r in fitting), default=None)
    passing = [r["ctx"] for r in fitting if r.get("retrieval_acc", 0) >= retrieval_threshold]
    return {
        "model": model,
        "axis": "capacity_retrieval",
        "gate_gb": gate_gb,
        "retrieval_threshold": retrieval_threshold,
        "records": records,
        "max_fitting_ctx": max_fitting,
        "capacity_gate_pass": any(r["ctx"] >= 256_000 for r in fitting),
        "retrieval_effective_ctx": max(passing, default=None),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd benchmark && python -m pytest bench/tests/test_scorecard.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add benchmark/bench/scorecard.py benchmark/bench/tests/test_scorecard.py
git commit -m "feat(bench): capacity+retrieval scorecard aggregation"
```

---

### Task 6: CLI entrypoint + calibration

**Files:**
- Create: `benchmark/bench/run_capacity.py`
- Create: `benchmark/bench/tests/test_run_capacity.py`

**Interfaces:**
- Consumes: everything above; `client.calibrate`-style chars/token (reuse the calibration approach from `needle_256k.calibrate_chars_per_token` but via the driver).
- Produces: `calibrate_cpt(driver, model) -> float`; `main(argv=None) -> int`. Writes `benchmark/results/<model>/capacity_retrieval.json` and `.../capacity_ladder.jsonl`.

- [ ] **Step 1: Write the failing test (calibration + output wiring, no network)**

Create `benchmark/bench/tests/test_run_capacity.py`:

```python
import json, os
import bench.run_capacity as R

class FakeDriver:
    def preload(self, model, timeout=900): return 1.0
    def complete(self, model, messages, params, timeout=3600):
        # calibration call asks for a known filler; return a prompt_tokens so cpt computes
        return {"content": "XKRZ0A7Q, XKRZ1B7Q, XKRZ2C7Q, XKRZ3D7Q, XKRZ4E7Q",
                "prompt_tokens": 100, "prefill_s": 1.0, "prefill_tps": 100,
                "decode_tps": 9.5, "peak_mem_gb": 40.0}

class FakeSampler:
    def __init__(self, **kw): pass
    def __enter__(self): return self
    def __exit__(self, *a): pass
    model_footprint_gb = 30.0
    system_peak_gb = 45.0
    peak_rss_gb = 0.0

def test_calibrate_returns_positive_cpt():
    assert R.calibrate_cpt(FakeDriver(), "m") > 0

def test_main_writes_results(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MlxServeDriver", lambda: FakeDriver())
    monkeypatch.setattr(R, "MemorySampler", FakeSampler)
    monkeypatch.setattr(R, "RESULTS", str(tmp_path))
    rc = R.main(["--model", "m", "--grid", "160000,192000"])
    assert rc == 0
    out = json.load(open(os.path.join(tmp_path, "m", "capacity_retrieval.json")))
    assert out["model"] == "m" and out["axis"] == "capacity_retrieval"
    assert len(out["records"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd benchmark && python -m pytest bench/tests/test_run_capacity.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'bench.run_capacity'`.

- [ ] **Step 3: Implement `run_capacity.py`**

Create `benchmark/bench/run_capacity.py`:

```python
"""CLI: run the capacity+retrieval ladder for one model on the box under test.

  cd benchmark && uv run python -m bench.run_capacity --model Qwen3.6-27B-UD-MLX-6bit

Writes benchmark/results/<model>/capacity_retrieval.json (+ capacity_ladder.jsonl)."""
import argparse
import json
import os

from .driver import MlxServeDriver
from .instrument import MemorySampler
from .capacity_ladder import run_ladder, DEFAULT_GRID, GATE_GB
from .scorecard import capacity_retrieval_scorecard

RESULTS = os.path.join(os.path.dirname(__file__), "..", "results")
_CAL_FILLER = "The quick brown fox jumps over the lazy dog near the riverbank at sunset. "


def calibrate_cpt(driver, model: str) -> float:
    out = driver.complete(model, [{"role": "user", "content": _CAL_FILLER * 200}],
                          {"max_tokens": 1, "temperature": 0.0}, timeout=120)
    chars = len(_CAL_FILLER * 200)
    pt = out.get("prompt_tokens") or 1
    return chars / pt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--grid", default=",".join(str(g) for g in DEFAULT_GRID))
    ap.add_argument("--gate-gb", type=float, default=GATE_GB)
    ap.add_argument("--no-preload", action="store_true")
    args = ap.parse_args(argv)
    grid = tuple(int(x) for x in args.grid.split(","))

    driver = MlxServeDriver()
    if not args.no_preload:
        driver.preload(args.model)
    cpt = calibrate_cpt(driver, args.model)
    print(f"[capacity] {args.model} cpt={cpt:.2f} grid={grid} gate={args.gate_gb}GB", flush=True)

    records = run_ladder(driver, args.model, cpt, grid=grid, gate_gb=args.gate_gb,
                         sampler_factory=MemorySampler)
    for r in records:
        print(f"[capacity] ctx={r['ctx']} footprint={r['model_footprint_gb']}GB "
              f"sys_peak={r['system_peak_gb']}GB acc={r['retrieval_acc']:.2f} "
              f"prefill={r['prefill_tps']}tok/s decode={r['decode_tps']}tok/s fits={r['fits']}",
              flush=True)

    sc = capacity_retrieval_scorecard(args.model, records, gate_gb=args.gate_gb)
    out_dir = os.path.join(RESULTS, args.model)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "capacity_ladder.jsonl"), "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(out_dir, "capacity_retrieval.json"), "w") as f:
        json.dump(sc, f, indent=2)
    print(f"[capacity] GATE_PASS={sc['capacity_gate_pass']} "
          f"max_fitting_ctx={sc['max_fitting_ctx']} "
          f"retrieval_effective_ctx={sc['retrieval_effective_ctx']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd benchmark && python -m pytest bench/tests/test_run_capacity.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Run the full harness unit suite**

Run: `cd benchmark && python -m pytest bench/tests/ -v`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add benchmark/bench/run_capacity.py benchmark/bench/tests/test_run_capacity.py
git commit -m "feat(bench): capacity+retrieval CLI entrypoint + calibration"
```

---

### Task 7: Acceptance run — the #1 measurement (real model, M5)

This task has no unit test; it is the real-world acceptance gate the whole MVP exists for. Run it on the M5 (`ssh $REMOTE_HOST`), where the fork + pool-cap path actually reach 256K.

**Files:** none changed (produces `benchmark/results/Qwen3.6-27B-UD-MLX-6bit/capacity_retrieval.json` on the M5 box).

- [ ] **Step 1: Get the harness onto the M5 box**

The stack repo on M5 is `~/Documents/ws/mlx_local_stack`. Sync the new `benchmark/bench/` code there (rsync avoids depending on a pushed remote):

```bash
rsync -av --delete benchmark/bench/ $REMOTE_HOST:~/Documents/ws/mlx_local_stack/benchmark/bench/
```

- [ ] **Step 2: Ensure the server is up with the model and the pool cap active**

On M5, start the stack (or confirm it's running) and confirm the auto-derived `mx.set_cache_limit` is applied (the load-bearing cap, mlx-vlm `cli.py`):

```bash
ssh $REMOTE_HOST 'cd ~/Documents/ws/mlx_local_stack && grep -i "cache.limit\|set_cache_limit\|cache_limit_gb" logs/main_model.log | tail -5'
```
Expected: a line showing the derived cache limit was set at startup. If absent, start the stack first (`./runserver.sh` / the `/mlx` flow) and re-check.

- [ ] **Step 3: Run the capacity ladder on the real model**

```bash
ssh $REMOTE_HOST 'cd ~/Documents/ws/mlx_local_stack/benchmark && uv run python -m bench.run_capacity --model Qwen3.6-27B-UD-MLX-6bit'
```
Expected: per-rung lines for 160K→256K with `footprint`, `acc`, `prefill`/`decode` tok/s, `fits`; then a final `GATE_PASS=...` line. (Each 256K prefill is minutes — the full ladder is tens of minutes. Consider running under `nohup`/background.)

- [ ] **Step 4: Record the verdict**

Read the result and write the finding into the program record:

```bash
ssh $REMOTE_HOST 'cat ~/Documents/ws/mlx_local_stack/benchmark/results/Qwen3.6-27B-UD-MLX-6bit/capacity_retrieval.json'
```
Capture: does `capacity_gate_pass` hold (256K footprint ≤ 46GB)? What is `max_fitting_ctx` and `retrieval_effective_ctx`? This **resolves Phase 1's #1 open question** (the 256K fit, previously only extrapolated from 200K). Append the numbers to `docs/sketches/2026-06-19-phase1-candidate-research.md` (or a new results sketch) and commit.

- [ ] **Step 5: Commit the result record**

```bash
git add docs/sketches/ benchmark/results/Qwen3.6-27B-UD-MLX-6bit/capacity_retrieval.json
git commit -m "results(bench): Qwen3.6-27B-6bit 256K capacity+retrieval measured on M5"
```

---

## Self-Review

**Spec coverage (Phase 0a slice):**
- Capacity gate ≤46GB (spec §7) → Tasks 4 (gate enforcement), 5 (gate verdict), 7 (real measurement). ✓
- Retrieval/capacity L-grid {160–256K} incremental (spec §7) → Task 4 `DEFAULT_GRID`, ladder loop. ✓
- Effective-length threshold 0.85 (spec §7) → Task 5 `retrieval_effective_ctx`. ✓
- Framework-agnostic driver / endpoint seam (spec §4.1) → Task 1 `Driver` protocol. ✓
- Instrumentation: peak RSS / footprint, TTFT (prefill proxy), prefill/decode tok/s, bottleneck field (spec §4.3) → Tasks 1, 2. (Bottleneck *tagging* logic is a stub field here; the compute-vs-bandwidth classifier is Phase 0b — noted, not silently dropped.)
- Scorecard normalization (spec §4.8) → Task 5 (capacity/retrieval slice only). ✓
- Runs on box under test, one-model-at-a-time, results dir (global constraints) → Tasks 6, 7. ✓
- **Deliberately deferred (not gaps):** reasoning axis 2b, agentic axis 3, judge panel 3q, execution sandbox, the full benchmark adapters, the bottleneck classifier, TTFT via streaming. These are Phase 0b/0c per the scope note.

**Placeholder scan:** no TBD/TODO; every code step has complete code; every command has expected output. The one intentional stub (`PerfRecord.bottleneck="unknown"`) is called out above, not hidden.

**Type consistency:** `complete()` return keys (Task 1) are consumed verbatim by `run_ladder` (Task 4); `PerfRecord` fields (Task 2) flow through `asdict` into ladder rows (Task 4) and are read by the scorecard (Task 5); `build_context`/`score` signatures (Task 3) match their ladder call sites (Task 4). `MemorySampler`/`MlxServeDriver` names match across Tasks 4 and 6. ✓

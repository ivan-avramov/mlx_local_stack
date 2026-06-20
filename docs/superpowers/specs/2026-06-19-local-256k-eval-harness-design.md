# Phase 0 — Local 256K Agentic-Coding Eval Harness

**Date:** 2026-06-19
**Status:** Design, pending review.
**Program:** This is Phase 0 of a four-phase program. Phase 0 builds the measuring stick; Phase 1 (landscape research, running as workflow `wf_8dd78f6e-d1e`) produces a candidate roster; Phase 2 characterizes each candidate's quality–speed frontier under technique sweeps; Phase 3 produces a model-selection decision guide. Each phase gets its own spec → plan.

## 1. Purpose

Build a framework-agnostic harness that produces a **single comparable scorecard** for any `(model × quant × KV-scheme × decode-accel × context-length)` configuration, so we can answer two questions with evidence rather than guesswork:

1. **Selection:** for a given local coding task at context length L, which model + config is the right tool?
2. **Technique attribution:** how much does each tuning knob (weight-quant, KV-quant, eviction, drafting) cost in quality and buy in speed/memory — and *why* (the bottleneck mechanism), so the finding transfers to a future NVIDIA H200/B200 deployment.

The harness is the most transferable artifact of the whole program. It must be correct, reproducible, and framework-agnostic before any model conclusion drawn from it is trustworthy.

### Non-goals

- Not a training/fine-tuning harness. Inference evaluation only.
- Not a serving/throughput benchmark (no batch-concurrency sweeps; we run batch-1, single-user). Concurrency is a B200 concern recorded as a *mechanism note*, not measured here.
- Does not itself implement techniques (TQ/OSCAR/EpiCache/MTP). It *measures* configurations; technique implementation is Phase 2.
- Not a leaderboard reproduction. We reuse trusted benchmarks; we do not re-derive their canonical numbers, only run the subsets we need under our configs.

## 2. The four axes and what measures each

| # | Axis | Instrument(s) | Scoring oracle |
|---|------|---------------|----------------|
| 1 | **Capacity** (gate) | Our instrumentation: load + run at target L | Objective: peak RSS, OOM/no-OOM, TTFT, tok/s |
| 2a | **Retrieval depth** | RULER (NIAH single/multi-key/value/query) | Objective: exact-match |
| 2b | **Reasoning depth** | RULER (variable-tracking, aggregation, QA) + NoLiMa; one built repo-reasoning probe | Objective (RULER/NoLiMa) + judge panel (repo probe) |
| 3 | **Agentic coding** | BFCL + τ-bench (tools); LiveCodeBench (single-shot); Aider polyglot + SWE-bench-Verified subset (agentic); IFEval (instructions) | Objective: execution / programmatic checks |
| 3q | **Code quality** (subjective) | Built judge-panel rubric over the 10 quality axes | Judge panel (mixed families), *layered on top of* execution-gated correctness |
| 4 | **Performance** | Our instrumentation during all of the above | Objective: TTFT, prefill tok/s, decode tok/s, peak RSS, bottleneck tag |

**Two effective-context curves.** Axes 2a and 2b are reported as accuracy-vs-L curves at L ∈ {8K, 32K, 64K, 128K, 256K}. Each model gets two headline numbers: retrieval effective-length and reasoning effective-length (the largest L at which accuracy ≥ a per-axis threshold, default 85%). These are reported separately and never conflated.

**Instrument/axis separation (do not cross-wire).** Recall/reasoning is scored by exact-match/MC oracles, never by the code-quality rubric. Code *correctness* is scored by execution (tests), never by the judge. The judge panel scores only the *subjective* code-quality axes where no oracle exists. Violating this mapping corrupts both measurements.

## 3. Architecture

```
                    ┌──────────────────────────────────────────────┐
                    │  runner.py  (config matrix, tiers, DoE/OFAT)   │
                    └──────────────────────────────────────────────┘
                          │                    │              │
                 ┌────────▼────────┐  ┌────────▼───────┐  ┌──▼──────────┐
                 │ endpoint driver │  │ instrumentation│  │  adapters/  │
                 │  (OpenAI-compat)│  │ (mem/TTFT/tok-s│  │  (per bench)│
                 │  MLX | llama.cpp│  │  /bottleneck)  │  └──┬──────────┘
                 └────────┬────────┘  └────────────────┘     │
                          │                                   │
                 ┌────────▼────────────────────────────┐  ┌──▼─────────────┐
                 │ model under test (any OpenAI server) │  │ scorers:       │
                 └──────────────────────────────────────┘  │  - exact/MC    │
                                                            │  - exec/tests  │
                                                            │  - judge panel │
                                                            └──┬─────────────┘
                                                               │
                                                    ┌──────────▼───────────┐
                                                    │ scorecard aggregator │
                                                    │ (composite, ε-gate,  │
                                                    │  Pareto export)      │
                                                    └──────────────────────┘
```

Built on the existing `benchmark/bench/` harness (generate→grade split, `client.py`, `model_params.py`, `run.py`). We extend rather than replace; `mem_decompose.py`, `needle_256k.py`, `validate_256k.py` fold in as instrumentation/adapters.

## 4. Components

Each is a single-purpose unit with a defined interface, independently testable.

### 4.1 Endpoint driver (`bench/driver.py`)
- **Does:** speaks the OpenAI chat/completions contract to any local server; abstracts MLX-serve and llama.cpp-server (and any OpenAI-compatible endpoint) behind one interface.
- **Interface:** `complete(messages, params) -> {text, usage, timings}` where `timings` carries server-reported prefill/decode splits when available (mlx-serve `timings.predicted_per_second`, llama.cpp `timings`).
- **Depends on:** an OpenAI-compatible HTTP endpoint. Extends current `client.py`.
- **Why framework-agnostic matters:** it's what lets MLX vs llama.cpp be compared apples-to-apples, and it's the seam where a future vLLM endpoint plugs in for B200 transfer.

### 4.2 Runner + config matrix (`bench/runner.py`)
- **Does:** expands a config spec into runs; enforces the tier (quick/heavy) and the DoE policy (cull → OFAT → combine); handles resume, one-model-at-a-time RAM safety (unload between models), and per-run isolation.
- **Interface:** `run(config_spec, tier) -> [RunResult]`.
- **DoE policy (built in, not ad hoc):** quick-vet culls the roster on a cheap subset; for survivors, sweep **one knob at a time** around a per-model baseline to isolate each technique's effect; only combine winning knobs and validate the stack. No full grid.
- **No premature shelving:** measure every plausible lever; do not a-priori drop a technique because its expected gain *seems* small (e.g. ~8%) — only exclude true mechanism category-errors (e.g. matmul/NA acceleration on a gather-bound decode). When in doubt, run it and let the harness quantify.
- **RAM safety:** never load two large models at once; `POST /v1/models/unload` between models (project constraint).

### 4.3 Instrumentation (`bench/instrument.py`)
- **Does:** captures per-run peak RSS, TTFT, prefill tok/s, decode tok/s, and a **bottleneck tag** (compute-bound / bandwidth-bound / memory-pool-bound), plus the weights-vs-KV memory split at the target L.
- **Interface:** wraps a run; emits a `PerfRecord`.
- **Depends on:** `mem_decompose.py` (extend), server timings, and macOS memory sampling on the box under test (over `ssh $REMOTE_HOST` for M5 runs).
- **Mechanism logging (B200 transfer requirement):** every PerfRecord records *why* (bottleneck + memory pool), because the verdict is hardware-specific but the mechanism is portable. A result without a mechanism tag is incomplete.

### 4.4 Benchmark adapters (`bench/adapters/`)
One adapter per external benchmark, each normalizing to a `{axis, score, raw, L}` record. **Reuse, do not reinvent** (see §6).
- `ruler.py` — self-generating to 256K; retrieval + reasoning subtasks; exact-match.
- `nolima.py` — latent reasoning, minimal lexical overlap; the honest effective-context measure.
- `bfcl.py`, `taubench.py` — tool-calling (quick / agentic).
- `livecodebench.py` — contamination-controlled single-shot coding.
- `aider_polyglot.py` — agentic edit-via-instruction + diff-format adherence.
- `swebench.py` — SWE-bench-Verified subset via an agent loop (heavy tier only).
- `ifeval.py` — programmatic instruction-following.
- Existing `aime`/`humanevalplus`/`mbppplus` retained for the quick tier.

### 4.5 Execution-gated correctness (`bench/exec_sandbox.py`)
- **Does:** runs generated code / tool outputs against tests in a sandbox; produces a hard pass/fail.
- **Why:** the judge is not a correctness oracle. Correctness is gated by execution *before* the judge ever sees the output; failing code cannot earn quality credit.

### 4.6 Judge panel (`bench/judge.py`)
- **Does:** scores the *subjective* code-quality axes only — correctness is already execution-gated — over the 10 axes: correctness-of-reasoning*, robustness, readability, maintainability, design/architecture, performance-awareness, security, testability, portability/compatibility, operational quality. (*the "correctness" rubric line is advisory commentary; the binding correctness signal is execution.)
- **Reliability controls (mandatory):** **mixed judge families** (not 3× the same model — that's one judge sampled thrice with correlated bias); blind + randomized presentation order; median (not mean) aggregation; rubric with explicit anchors per score level.
- **Interface:** `judge(task, candidate_output, reference?) -> {axis_scores, rationale}`.
- **Default panel:** Sonnet, Opus, and GPT-5.5 (the last via the `codex` CLI). This is 2 Anthropic + 1 OpenAI; self-preference bias is largely moot because the models *under test* are Qwen/Gemma (no judge grades its own family), but Sonnet/Opus may share a correlated code-aesthetic prior — mitigated by reporting **per-judge scores** (not just the median) and treating large Anthropic-vs-OpenAI splits as low-confidence. The judge backend abstracts three implementations: Anthropic API (Sonnet, Opus) and a one-shot `codex` invocation (GPT-5.5).

### 4.7 Long-code reasoning (`bench/adapters/longcode.py`) — *use existing*
- **Does:** workload-representative long-context *code* reasoning. Standard testbeds exist — reuse rather than build: **LongCodeBench** (to 1M ctx), **LongCodeU**, **RepoQA** (find-the-function across a repo, 5 languages), **Long Code Arena**, **LoCoBench**. SWE-bench-Verified already exercises reason-over-a-repo-to-act.
- **Build only if needed:** a thin "produce an architectural plan over a large repo, judge the plan" wrapper, *only* if none of the above match the design-plan framing at our reasoning L-grid. Default is to reuse.

### 4.8 Scorecard aggregator (`bench/scorecard.py`)
- **Does:** merges objective + judged + perf records into one comparable scorecard per config; computes the composite, applies the **quality-neutral ε gate**, and exports the **quality–vs–speed Pareto frontier** per model and overlaid across models.
- **Interface:** `aggregate([records]) -> Scorecard`; `pareto(scorecards) -> frontier`.

## 5. Tiers

| | Quick vet (minutes; M2 OK) | Heavy / proper (hours; M5 via `ssh $REMOTE_HOST`) |
|---|---|---|
| Purpose | Cull the roster cheaply | Rank + characterize survivors |
| Capacity | loads + runs 256K in budget; peak RSS; tok/s @128K | full mem decompose; tok/s sweep @8K/64K/256K |
| Retrieval | 5× RULER-NIAH @64K & 256K | RULER retrieval suite across all L |
| Reasoning | 2× multi-hop @64K & 256K | RULER reasoning suite + NoLiMa across all L + repo probe |
| Coding | 3 tool-call cases; 2–3 Aider exercises; IFEval subset; existing AIME/HE+/MBPP+ | BFCL + τ-bench; LiveCodeBench; Aider polyglot full; SWE-Verified subset; IFEval full |
| Perf | tok/s + mem @8K & 128K | full sweep + quality-neutrality regression per technique |

## 6. Use-vs-build decision (locked)

~80% reuse trusted, mostly-objective external benchmarks; ~20% build only what is specific to our workload.

| Need | Decision | Note |
|---|---|---|
| Retrieval depth | **Use** RULER | synthetic to 256K, exact-match |
| Reasoning depth | **Use** RULER + NoLiMa | NoLiMa kills the n-gram-match illusion |
| Reasoning, our workload | **Use** LongCodeBench / LongCodeU / RepoQA / Long Code Arena / LoCoBench | build only a thin design-plan wrapper if none fit |
| Tool calling | **Use** BFCL + τ-bench | |
| Coding single-shot | **Use** LiveCodeBench | replaces saturated HE+/MBPP+ for ranking |
| Coding agentic | **Use** Aider polyglot + SWE-Verified subset | |
| Instruction following | **Use** IFEval | |
| Code quality (subjective) | **Build** judge-panel rubric | the one genuinely missing instrument |
| Capacity + perf | **Build** instrumentation glue | extends mem_decompose/validate_256k |

## 7. Gates and definitions

- **Capacity gate:** peak ≤ **46GB** at 256K (usable profile) — pass/fail. Secondary "browser-closed" profile ≤ **56GB** reported but not gating.
- **Interactive floors (reported; tunable):** cold-256K TTFT ≤ ~90s; long-context decode ≥ ~15 tok/s. These flag usability, not hard-fail, since the workload front-loads reasoning (one big latency-tolerant prefill) and decode is the per-turn ongoing cost — report prefill-TTFT and decode-tok/s **separately**, weighted by session shape (1 prefill + N implementation turns).
- **Quality-neutral ("not noticeable"):** a technique is quality-neutral if it drops the composite by ≤ **5%**, **per-axis adjustable** (tighter on correctness/recall, looser on style). A technique that trips the ε gate on any guarded axis is flagged as quality-affecting.
- **Effective-length threshold:** accuracy ≥ 85% (per-axis adjustable), measured over N≥20 items per (L, task-type) rung.
- **Retrieval/capacity grid (incremental-fill):** {160K, 192K, 224K, 256K} — keep filling the *same* context in 32K chunks, capturing RSS at each step; the capacity gate fails the moment peak > 46GB. Each fill level also scores needle accuracy at multiple depths. No smaller windows (retrieval is trivially fine there).
- **Reasoning grid (climb-to-cliff):** {8K, 16K, 24K, 32K, 48K, 64K} per reasoning task-type — test a rung only if the one below passed; stop at the first fail (the cliff). A second pass bisects the last-pass/first-fail interval (e.g., 28K between 24K and 32K) to localize the ceiling. Report the cliff **per task-type** (2-hop / aggregation / variable-tracking); the model's reasoning headline is the *minimum* cliff across types plus the breakdown.

## 8. Data flow

1. Runner expands `(model, config, tier)` → run plan (DoE-aware).
2. Driver boots/targets the endpoint; instrumentation begins sampling.
3. Adapter feeds prompts at each L; driver returns outputs + timings.
4. Objective scorers (exact-match/MC) score recall/reasoning; exec sandbox gates code correctness; judge panel scores subjective code-quality on passing outputs only.
5. Instrumentation finalizes PerfRecords (with bottleneck + memory-pool tags).
6. Aggregator emits the scorecard, applies ε gate, exports Pareto frontier.
7. Results land in `benchmark/results/<model>/<config>/<tier>.json` (+ a roll-up table).

## 9. Reproducibility & error handling

- **Determinism:** fixed seeds, fixed prompt sets, temperature pinned per task (greedy for objective scoring; task-appropriate for coding). Record model build hash, framework version, quant id, KV-scheme, and box (M2/M5).
- **Resume:** runs are idempotent and resumable per `(model, config, L, adapter)`; a crashed long run resumes without redoing completed cells.
- **Failure isolation:** an adapter or judge failure drops that cell to `null` with a logged reason; it never silently scores 0 (which would corrupt rankings) and never aborts the batch.
- **No silent caps:** any sampling/subset/truncation (e.g., SWE-Verified subset size) is logged in the scorecard so partial coverage never reads as full coverage.
- **RAM safety:** one large model resident at a time; unload between models.

## 10. Testing the harness itself

- Unit: each scorer against known-answer fixtures (exact-match, exec pass/fail, judge schema).
- Contract: driver against both an MLX-serve and a llama.cpp-server stub returning canned timings.
- Golden: a tiny end-to-end run on a small model produces a stable scorecard shape.
- Judge calibration: a held-out set with known-good/known-bad code confirms the panel separates them and that order/family randomization changes scores within tolerance.

## 11. Open questions

- **L grids — RESOLVED** (§7): retrieval/capacity {160K,192K,224K,256K} incremental-fill with RSS gate; reasoning {8,16,24,32,48,64K} climb-to-cliff + bisection.
- **Judge panel — RESOLVED** (§4.6): Sonnet + Opus + GPT-5.5/codex.
- **Long-code reasoning — RESOLVED** (§4.7): reuse existing testbeds; confirm one runs at our reasoning L-grid during planning.
- **SWE-Verified subset size (open):** recommend a fixed stratified **30–50 issues** for the heavy first pass (rank-able in hours); expand to ~100 only if two models tie within noise. Confirm the number.
- **Perf reporting (recommend, confirm):** report prefill-TTFT and decode-tok/s **separately**; do *not* collapse to one scalar (matches "validate quantitatively"). A single weighted score is only needed if you want one ranking number — if so, supply a session shape (generate-turns per big prefill, ~tokens/turn).
- **Decode-floor lever (don't shelve):** dense Qwen decodes below the 15 tok/s floor at long ctx and suffix gives ~0 on novel gen; queue the MTP-head re-convert as a Phase-2 item to validate the ~1.5–2.5× claim rather than assume it.

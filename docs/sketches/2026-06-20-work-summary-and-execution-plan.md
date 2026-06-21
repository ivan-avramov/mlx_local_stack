# Work summary (all phases) + execution plan

**Date:** 2026-06-20. **Purpose:** the pre-execution checkpoint — what's been built, what remains to build, and exactly how the real benchmark campaign will run, before any compute is spent.

---

## Part 1 — Program recap

**Goal:** evidence-based pick of local LLM(s) for **256K-context agentic coding on a 64GB Mac**, plus techniques/methodology transferable to future H200/B200 work. Phase 1 = **Selection** (measure candidates at baseline across capacity → retrieval → reasoning → agentic-coding → tool-calling, then pick daily-driver + reasoner). Phase 2 = **Optimization** (perf levers on the winner, quality-neutral) — later.

**The two candidates (bake-off):**
- **Qwen3.6-27B-UD-MLX-6bit** — dense + GatedDeltaNet. Reasoner/quality. Fits 192K@46GB (256K@56GB browser-closed), decode ~4–6 tok/s.
- **gemma-4-26B-A4B-it-QAT-MLX-4bit** — MoE + sliding-window. Daily/speed+capacity. Only 256K-@46GB fitter (40.5GB), decode ~12–26 tok/s.

**Already measured (prior sessions):** capacity (MLX-peak gate), light variable-tracking reasoning (both ≥64K), Qwen retrieval 1.0→256K (gemma's was thinking-contaminated — fixed by the new retrieval probe, not yet re-run).

---

## Part 2 — Tooling built this session (Phase-1 measuring stick)

All built subagent-driven (TDD, per-task review, opus final review), each merged to `main`, full suite **110 passed / 1 skipped**. Every external dependency is **lazy-imported + graceful-degrade + mocked in tests**, so the harness is green without any heavy deps installed; the real deps install only where each runs.

| # | Tooling | Measures | Status | Real-run dependency |
|---|---------|----------|--------|---------------------|
| 1 | Retrieval probe (`run_retrieval`) | NIAH multi-needle accuracy-vs-ctx curve (production params) | ✅ merged `6393195` | none (synthetic) |
| 2 | LiveCodeBench grading (`grade_lcb`) | single-shot coding pass@1 (contamination-pinned) | ✅ merged `456ead2` | `lcb_runner` |
| 3 | IFEval (`grade_ifeval`) | instruction-following (official vendored verifiers) | ✅ merged `8e775c2` | absl-py/langdetect/nltk/immutabledict |
| 4 | BFCL (`run_bfcl`) | single-turn tool-calling (drives official `bfcl-eval`) | ✅ merged `3f56d84` | `bfcl-eval`, model served |
| 5 | Heavy reasoning (`run_aggregation`, `run_latent`) | RULER-aggregation + NoLiMa-style latent (auto-extend past 64K) | ✅ merged `b0acdd3` | none (synthetic) |
| 6 | Agentic coding (`exec_sandbox` + `agent_loop` + Aider + SWE-Verified-40) | agentic edit + repo-issue resolution | **TO BUILD** | aider+polyglot, swebench+docker, model served |
| 7 | Judge panel (Sonnet+Opus+codex) | subjective code-quality rubric over passing outputs | **TO BUILD** | Anthropic API, codex CLI |

**Locked methodology decisions (the frame):**
- **Production params verbatim** — every quality run uses `bench/model_params.py:params_for(model)` (temp/top_p/top_k/min_p/penalties + enable_thinking + thinking_budget [hard headroom cap] + max_tokens). No greedy, no ad-hoc budgets.
- **Capacity metric = MLX peak** (`mx.get_peak_memory`, the prefill spike = OOM trigger); RSS reported alongside. Gate ≤46GB@256K usable / ≤56GB browser-closed.
- **Two effective-context curves, never conflated:** retrieval depth vs reasoning depth.
- **Instrument/axis separation:** recall/reasoning → exact-match; code correctness → execution; subjective code quality → judge panel only (judge is not a correctness oracle).
- **Effective-length threshold** ≥85%; reasoning ladders climb-to-cliff + auto-extend past 64K in 8K steps.
- **B200 transfer:** log the bottleneck/mechanism (compute vs bandwidth, which memory pool) per result — verdicts are HW-specific, mechanisms portable.

**Two deviations to flag (decided autonomously, justified):**
1. **NoLiMa is a self-authored *style* probe**, NOT the official `amodaresi/NoLiMa` dataset (Adobe Research License — restrictive; avoided for transferable, self-contained tooling). Measures *relative* latent-reasoning depth, not leaderboard parity. Official-dataset swap is a documented future option. (Rollup also notes one association, #15 econ, has a thin lexical gap — optional harder swap recorded.)
2. **τ-bench dropped** (per your fork-B B1 choice): tool-calling-agentic overlaps BFCL + the judge for the coding bake-off; lowest marginal value.

---

## Part 3 — Remaining build (#6, #7) — mock-tested, before any real run

Per your confirmation, these get the same mock-tested discipline as #1–#5; the real Aider/SWE/docker/judge runs are execution-phase (I drive).
- **#6 agentic coding:** `exec_sandbox.py` (run code/patches vs tests in a sandboxed subprocess, timeout) + `agent_loop.py` (generic tool-calling loop on our Driver) — both high-confidence, fully unit-tested; + `aider_adapter`/`run_aider` (orchestrate aider's polyglot benchmark against mlx-serve, parse `pass_rate_#`) + `swebench_adapter`/`run_swebench` (minimal patch-gen agent on the infra → predictions JSONL → `swebench.harness.run_evaluation` → resolved count), both lazy/graceful-degrade + mock-tested.
- **#7 judge panel:** `judge.py` — mixed families (Anthropic Sonnet+Opus + GPT-5.5 via codex CLI), blind+randomized order, median + per-judge, scores the subjective rubric only over execution-passing outputs. Lazy/graceful-degrade + mock-tested.

**Est. remaining build:** ~2 plans, subagent-driven like the prior five.

---

## Part 4 — EXECUTION PLAN (the real benchmark campaign)

Nothing here runs until you approve. The campaign produces the Step-3 scorecard → daily-driver vs reasoner decision.

### 4.1 Boxes & constraints (hard rules)
- **M5 Max** (`ssh $REMOTE_HOST`, ~7× faster, clean) — heavy/long runs. **M2 Max** (local dev) — lighter runs + grade-time work (judges, IFEval/LCB grading) that doesn't load a model.
- **One model resident at a time**; `POST /v1/models/unload` between models; **keep the box quiet** during a run (MLX-peak gate is robust, RAM headroom isn't).
- Lean router (no OWUI/docker): `MLX_SERVE_CONFIG=main_models.yaml uv run mlx-serve start`; on M5 prepend `PATH=/opt/homebrew/bin:$PATH` and `set -a; . ./.env; set +a`.
- Long-context runs are RAM-bound: Qwen 256K only browser-closed/M5; gemma 256K fits.

### 4.2 One-time installs (B3 — I drive these, per box/role)
- **Model-server boxes (M5/M2):** nothing extra (mlx-serve already serves the candidates).
- **Grade/agent box (M2 dev):** `uv pip install -r benchmark/requirements.txt` (datasets, evalplus, math-verify, IFEval deps); `uv pip install "git+…/LiveCodeBench"` (lcb_runner); `uv pip install bfcl-eval==2025.12.17`; `uv pip install aider-chat` + clone polyglot-benchmark; `uv pip install swebench` + **docker** (large images); `codex` CLI authed + `ANTHROPIC_API_KEY` for judges.
- **Validation-first:** each adapter gets a tiny smoke run (e.g. BFCL `--limit 5`, Aider `--num-tests 2`, SWE 1–2 instances) to confirm the integration before the full run — this is where the run-time-validated boundaries (BFCL `--model` handler, LCB accessor, aider `--model openai/<name>` mapping, swebench docker) get confirmed.

### 4.3 Run matrix (both candidates unless noted)
Ordered cheapest→heaviest / most-decisive-first; **synthetic probes need no installs** so they go first.

| Order | Run | Box | Loads model? | Notes / est. |
|---|---|---|---|---|
| 1 | Retrieval curve (`run_retrieval`) | gemma→M2, Qwen 192K/256K→M5 | yes | clean retrieval curve; closes gemma cleanup |
| 2 | Heavy reasoning: aggregation + latent | M5 (long, auto-extend) | yes | the honest reasoning ceiling — likely where dense-hybrid vs MoE diverge |
| 3 | IFEval (generate→grade) | gen: model box; grade: M2 (deps) | gen yes | instruction-following |
| 4 | LiveCodeBench (generate→grade) | gen: model box; grade: M2 (lcb_runner) | gen yes | single-shot coding |
| 5 | BFCL (`run_bfcl`) | model box + bfcl-eval | yes | tool-calling; smoke `--limit 5` first |
| 6 | Aider polyglot | model box + aider | yes | agentic edit; `--num-tests` subset first, then core |
| 7 | SWE-Verified-40 | model box + docker (heavy) | yes | heaviest; stratified 40; docker per instance |
| 8 | Judge panel over passing coding outputs | M2 (no model; cloud judges) | no | subjective rubric; median + per-judge |

**Per model: load → run its block → unload → swap.** (Minimizes swaps; one model resident.) Or interleave per-axis if a balanced partial read is wanted earlier.

### 4.4 Synthesis → decision (Step 3, closes Phase 1)
One scorecard across the 2 candidates: **capacity × retrieval-eff-len × latent-reasoning-eff-len × agentic-coding (LCB/Aider/SWE, execution-gated) × tool-calling (BFCL) × instruction-following (IFEval) × code-quality (judge median, per-judge reported) × speed (prefill-TTFT + decode-tok/s separately).** Apply the gates; report the daily-driver vs reasoner pick with quantified tradeoffs + the bottleneck/mechanism notes for B200 transfer. Update `main_models.yaml` roles + write the decision guide. Then Phase 2 (MTP first).

### 4.5 Risks / watch-items
- **RAM/OOM:** long-ctx Qwen on M5 browser-closed only; unload between; keep quiet.
- **SWE-bench:** docker images are large + slow; 40 instances is hours; start with 1–2 to validate, then batch on M5.
- **BFCL `--model` handler:** must map our served name to a handler whose prompt/decode matches (resolved at smoke-run).
- **Judges:** codex CLI auth + Anthropic key; cloud spend (you OK'd it); large Anthropic-vs-OpenAI splits flagged low-confidence.
- **Thinking budget:** hard headroom cap; models finish ≤~10K so headroom is free — never lower enough to truncate.
- **NoLiMa-style caveat** (above) — relative signal valid; absolute parity needs the official dataset.

---

## Decision points for you
1. **Finish building #6 + #7 first, then run the campaign?** (Recommended — completes the measuring stick before any compute.) Or run the already-built probes (1–5) now and build #6/#7 in parallel?
2. **Run ordering** — cheapest-first as above (synthetic reasoning/retrieval before the install-heavy coding/agentic), or prioritize a specific axis?
3. **SWE-Verified subset = 40** confirmed? (stratified; expand to ~100 only on a tie.)
4. Anything to add/cut from the run matrix before I start driving installs + smoke runs.

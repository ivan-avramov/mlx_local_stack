# Campaign Results & Rankings (living)

Tracks results and rankings for every candidate (model, config) in the local-LLM selection campaign: picking the best LOCAL LLM + config for 256K-context agentic coding on a 64GB Apple-Silicon Mac. Evaluation is breadth-first across escalating tiers — LIGHT (humanevalplus N=10, mbppplus N=10, aime N=5) across all archs → MID (livecodebench per-difficulty, ifeval, math500) on survivors → HEAVY (full sets, gpqa, agentic axes Aider / SWE-40, judge panel). Thinking is ENABLED for all tests. NO model/arch is pruned on partial results; ranking is decided only across the full suite.

**Current phase: light-tier broad sweep.**

## Sampling config (per-arch)

Sampling is per-ARCH, not unified. Each model runs at its own arch's config.

### gemma (dense + MoE) — PRODUCTION sampling

`temperature 0.7, top_p 0.95, top_k 64, repetition_penalty 1.08`

The "official" gemma rec (temp 1.0, rep_pen 1.0) causes degenerate repetition loops. Confirmed by a controlled 2×2 on HumanEval/146: temp 1.0 loops at both rep_pen 1.0 and 1.08; temp 0.7 converges at both. Temperature is the lever; rep_penalty is irrelevant and backfires. The earlier "restart fixes the stale router" was an RNG-reroll lottery, not causal — see root-cause note below.

### Qwen3.6 (incl. the Opus-distill, Qwen-arch) — OFFICIAL coding sampling

`temperature 0.6, top_p 0.95, top_k 20, min_p 0, presence_penalty 0`

Qwen converges fine at official params; its issue is genuine verbosity, not loops. Penalties are avoided for Qwen: the vendor card warns `presence_penalty` causes language-mixing, and an N=1 production-presence-0.3 sample looped it. A verbosity hill-climb is planned (top_k 20→10→5, then temp / top_p / min_p), measuring tokens AND pass@1.

## Results scoreboard

Light tier, each model at its per-arch sampling above. Graded via the official EvalPlus evaluator run in docker. `conv%` = convergence rate (`finish=stop AND completion < thinking_budget`); a run with any non-convergence is marked INVALID regardless of pass@1.

| Model | Sampling | Benchmark | Tier | N | pass@1 | conv% | valid? |
|---|---|---|---|---|---|---|---|
| gemma-4-26B-A4B-it-OptiQ-4bit (MoE) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-26B-A4B-it-OptiQ-4bit (MoE) | production t0.7 | mbppplus | light | 10 | 80% (8/10) | 90% (1 loop Mbpp/610) | INVALID |
| gemma-4-26B-A4B-it-OptiQ-4bit (MoE) | production t0.7 | aime | light | 5 | 80% (4/5) | 60% (2 loops) | INVALID |
| Qwen3.6-27B-UD-MLX-6bit-kv16 (dense) | official t0.6 | humanevalplus | light | 10 | 90% (9/10) | 100% | VALID |
| Qwen3.6-27B-UD-MLX-6bit-kv16 (dense) | official t0.6 | mbppplus | light | 10 | 80% (8/10) | 100% | VALID |
| Qwen3.6-27B-UD-MLX-6bit-kv16 (dense) | official t0.6 | aime | light | 5 | 80% (4/5) | 80% (1 loop aime25-3) | INVALID |
| gemma-4-26b-a4b-it-8bit (MoE) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-26b-a4b-it-8bit (MoE) | production t0.7 | mbppplus | light | 10 | 80% (8/10) | 80% (2 loops) | INVALID |
| gemma-4-26b-a4b-it-8bit (MoE) | production t0.7 | aime | light | 5 | 40% (2/5) | 0% (all 5 loop) | INVALID |
| gemma-4-26b-a4b-it-4bit (MoE, vanilla-4bit) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-26b-a4b-it-4bit (MoE, vanilla-4bit) | production t0.7 | mbppplus | light | 10 | 80% (8/10) | 90% (1 loop) | INVALID |
| gemma-4-26b-a4b-it-4bit (MoE, vanilla-4bit) | production t0.7 | aime | light | 5 | 60% (3/5) | 20% | INVALID |
| gemma-4-26B-A4B-it-QAT-MLX-4bit (MoE) | production t0.7 | humanevalplus | light | 10 | 90% (9/10) | 60% (4 loops) | INVALID |
| gemma-4-26B-A4B-it-QAT-MLX-4bit (MoE) | production t0.7 | mbppplus | light | 10 | 70% (7/10) | 40% (6 loops) | INVALID |
| gemma-4-26B-A4B-it-QAT-MLX-4bit (MoE) | production t0.7 | aime | light | 5 | 40% (2/5) | 20% | INVALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | mbppplus | light | 10 | 70% (7/10) | 90% (1 loop) | INVALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | aime | light | 5 | 80% (4/5) | 80% (1 loop) | INVALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | official t0.6 | humanevalplus / mbppplus / aime | light | — | pending (M5) | — | — |

Quant ladder still to run: Qwen MLX-8bit / OptiQ-4bit / oMLX-6bit; gemma dense qat-6bit.

## Methodology & validation notes

- Graded via the official EvalPlus evaluator in docker: code extraction → official docker evalplus execution → per-test results. Pipeline verified working 2026-06-24 (it discriminates correct vs subtly-buggy code — see below).
- `conv%` is enforced as a hard validity gate. A run that hits the `thinking_budget` (or truncates mid-`<think>`) is a FAIL signal to investigate, never lowered to "pass." Several light runs are INVALID on convergence even at high pass@1; rerun before they count.
- Two boxes, one model each (M2 local, M5 remote). Light-tier assignment is by arch to parallelize. Sampling, KV scheme, and box are recorded per row for auditability.
- N=10 / N=5 light samples carry variance; treat differences as relative signal, not leaderboard parity.
- MoE quant sensitivity (light, production t0.7): OptiQ-4bit, 8bit, and vanilla-4bit all converge cleanly on easy coding (HumanEval+ 100% conv); **QAT-MLX-4bit is loop-prone** (HumanEval+ conv 60%, MBPP+ conv 40% — 4-6 loops) even at production temp — a quant-specific defect, not the temp-1.0 issue. ALL MoE quants loop on hard reasoning (aime conv 0-60%) — the 4B-active arch limit. Coding pass@1 is similar across the non-QAT MoE quants (HE+ 90-100% / MBPP+ 70-80%).
- IFEval axis currently UNAVAILABLE: the `datasets` load fails with "Feature type 'List' not found" (a datasets-version incompatibility with the google/IFEval schema). Needs a fix before instruction-following can run; the sweep skips it gracefully (acc:null, no crash).

### EvalPlus validation (2026-06-24)

Qwen's 90% vs gemma-MoE's 100% on HumanEval+ is an N=10, single-item difference, NOT a ranking. The one Qwen miss is HumanEval/97 (`multiply` = product of unit digits): its `(a%10)*(b%10)` is correct on base HumanEval but wrong for negatives (Python `-6%10==4`, not 6), so it fails the HumanEval+ extra test `[-6,-9]` (base=pass, plus=fail) — exactly what HumanEval+ is designed to catch; gemma handled the negative case. Magnitude matches published: the Qwen3.6 family scores ~90.2% HumanEval+ pass@1 on full EvalPlus (35B-A3B sibling, EvalPlus leaderboard issue #299). The eval discriminates correct vs subtly-buggy code (Qwen fail vs gemma pass on the same problem). Both archs are strong on easy coding (~90–100%); they do NOT separate at the light tier — differentiation is expected at mid (LCB per-difficulty) / heavy (agentic).

### Provenance

Grading detail and the stale-router / temp-1.0 root cause live in git history (commits through acad470) and `AGENTS.md`.

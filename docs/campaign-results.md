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
| gemma-4-26B-A4B-it-OptiQ-4bit (MoE) | production t0.7 | **livecodebench** | **mid** | 15 | 80% (E100/M86/H60) | 73% (4 loops) | INVALID |
| gemma-4-26b-a4b-it-8bit (MoE) | production t0.7 | **livecodebench** | **mid** | 15 | 80% (E100/M86/H60) | 80% (3 loops) | INVALID |
| gemma-4-26b-a4b-it-4bit (MoE, vanilla-4bit) | production t0.7 | **livecodebench** | **mid** | 15 | 66.7% (E100/M71/H40) | 7% (14 budget-hit) | INVALID |
| gemma-4-26B-A4B-it-QAT-MLX-4bit (MoE) | production t0.7 | **livecodebench** | **mid** | 15 | 66.7% (E100/M57/H60) | 33% (10 budget-hit) | INVALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | **livecodebench** | **mid** | 15 | **86.7% (E100/M86/H80)** | 80% (3 budget-hit) | INVALID |
| gemma-4-31b-it-UD-MLX-4bit (dense) | production t0.7 | **livecodebench** | **mid** | 15 | **86.7% (E100/M86/H80)** | 93% (1 budget-hit) | INVALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | mbppplus | light | 10 | 70% (7/10) | 90% (1 loop) | INVALID |
| gemma-4-31b-it-6bit (dense) | production t0.7 | aime | light | 5 | 80% (4/5) | 80% (1 loop) | INVALID |
| gemma-4-31b-it-UD-MLX-4bit (dense) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-31b-it-UD-MLX-4bit (dense) | production t0.7 | mbppplus | light | 10 | 80% (8/10) | 100% | VALID |
| gemma-4-31b-it-UD-MLX-4bit (dense) | production t0.7 | aime | light | 5 | 60% (3/5) | 100% | VALID |
| gemma-4-31B-it-qat-6bit (dense) | production t0.7 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| gemma-4-31B-it-qat-6bit (dense) | production t0.7 | mbppplus | light | 10 | 80% (8/10) | 100% | VALID |
| gemma-4-31B-it-qat-6bit (dense) | production t0.7 | aime | light | 5 | **100% (5/5)** | 100% | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (Qwen-arch) | official t0.6 | humanevalplus | light | 10 | 90% (9/10) | 100% | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (Qwen-arch) | official t0.6 | mbppplus | light | 10 | 80% (8/10) | 100% | VALID |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (Qwen-arch) | official t0.6 | aime | light | 5 | 80% (4/5) | 40% (3 loops) | INVALID |
| Qwen3.6-27B-OptiQ-4bit (Qwen-arch) | official t0.6 | humanevalplus | light | 10 | 100% (10/10) | 100% | VALID |
| Qwen3.6-27B-OptiQ-4bit (Qwen-arch) | official t0.6 | mbppplus | light | 10 | 80% (8/10) | 100% | VALID |
| Qwen3.6-27B-OptiQ-4bit (Qwen-arch) | official t0.6 | aime | light | 5 | 80% (4/5) | 80% (1 loop aime25-14) | INVALID |

Quant ladder still to run: Qwen MLX-8bit / OptiQ-4bit / oMLX-6bit; gemma dense qat-6bit.

## Methodology & validation notes

- Graded via the official EvalPlus evaluator in docker: code extraction → official docker evalplus execution → per-test results. Pipeline verified working 2026-06-24 (it discriminates correct vs subtly-buggy code — see below).
- `conv%` is enforced as a hard validity gate. A run that hits the `thinking_budget` (or truncates mid-`<think>`) is a FAIL signal to investigate, never lowered to "pass." Several light runs are INVALID on convergence even at high pass@1; rerun before they count.
- Two boxes, one model each (M2 local, M5 remote). Light-tier assignment is by arch to parallelize. Sampling, KV scheme, and box are recorded per row for auditability.
- N=10 / N=5 light samples carry variance; treat differences as relative signal, not leaderboard parity.
- MoE quant sensitivity (light, production t0.7): OptiQ-4bit, 8bit, and vanilla-4bit all converge cleanly on easy coding (HumanEval+ 100% conv); **QAT-MLX-4bit is loop-prone** (HumanEval+ conv 60%, MBPP+ conv 40% — 4-6 loops) even at production temp — a quant-specific defect, not the temp-1.0 issue. ALL MoE quants loop on hard reasoning (aime conv 0-60%) — the 4B-active arch limit. Coding pass@1 is similar across the non-QAT MoE quants (HE+ 90-100% / MBPP+ 70-80%).
- **DENSE converges where MoE loops (emerging differentiator).** The dense gemma-4-31B candidates converge cleanly on hard reasoning where every MoE quant loops: gemma-4-31B-it-**qat-6bit** is the leader — light HE+ 100% / MBPP+ 80% / **AIME 100% (5/5) at 100% convergence**, the best reasoning result + cleanest convergence in the campaign. dense 6bit & UD-4bit are also ~clean. And the dense BEATS the MoE on LCB itself — both gemma-4-31b-it-6bit and gemma-4-31b-it-UD-MLX-4bit score **86.7% (E100/M86/H80)** vs the MoE's 80% (E100/M86/**H60**), with the gap on HARD (80% vs 60%) AND cleaner convergence (UD-4bit 14/15=93%, 6bit 12/15=80% vs MoE 73–80%) — all at the SAME production budget 16384. Mechanism: the 4B-active MoE over-reasons/loops on hard items; the full-dense models reason concisely, self-terminate, and solve more. This favors the dense candidates on BOTH coding accuracy and convergence (the MoE's only edge is decode speed).
- IFEval axis currently UNAVAILABLE: the `datasets` load fails with "Feature type 'List' not found" (a datasets-version incompatibility with the google/IFEval schema). Needs a fix before instruction-following can run; the sweep skips it gracefully (acc:null, no crash).
- **MoE quant thinking-efficiency on LCB (apples-to-apples, all at production t0.7 / thinking_budget 16384 / max_tokens 32768):** the three MoE quants diverge sharply in *reasoning verbosity*, which drives both convergence and accuracy. 8bit is the most efficient (median 8031 thinking tokens, 12/15 converged), OptiQ-4bit close behind (median 11563, 11/15), but **vanilla-4bit's median (17116) EXCEEDS the budget** → 14/15 budget-hit, conv 1/15. The over-thinking costs accuracy precisely on the harder problems (pass@1 66.7% E100/M71/H40 vs 80% E100/M86/H60 for the calibrated quants) — truncated reasoning forces premature answers. This is a genuine quant defect (uncalibrated 4-bit degrades reasoning efficiency), confirmed apples-to-apples (identical budget/max_tokens/profile; not a harness artifact, not the sleep). Conclusion for the MoE: **OptiQ calibration is worth it — 8bit ≈ OptiQ-4bit ≫ vanilla-4bit**; lowering the budget would NOT "fix" vanilla-4bit (the discipline forbids it), the budget is appropriate (the better quants fit inside it).
- LCB grading requires `PYTHONPATH=$HOME/.cache/livecodebench/LiveCodeBench` (the checkout); without it `grade_lcb` degrades gracefully to `lcb_runner not available` / acc:null (so a forgotten PYTHONPATH is a visible skip, not a silent wrong number). LCB grading (mid tier) runs via `lcb_runner` directly and DOES work on macOS (no docker needed — unlike evalplus); validated on the gemma-MoE-OptiQ-4bit LCB run. The per-difficulty breakdown (Easy/Medium/Hard) is where archs are expected to separate — light-tier coding clustered at ~70-100% with no separation, but LCB already shows a gradient (OptiQ-4bit: E100/M86/H60). LCB still flags loops on AtCoder/stdin (the over-thinking trigger) -> INVALID until investigated, but the converged per-difficulty pass@1 is the differentiating signal.

### EvalPlus validation (2026-06-24)

Qwen's 90% vs gemma-MoE's 100% on HumanEval+ is an N=10, single-item difference, NOT a ranking. The one Qwen miss is HumanEval/97 (`multiply` = product of unit digits): its `(a%10)*(b%10)` is correct on base HumanEval but wrong for negatives (Python `-6%10==4`, not 6), so it fails the HumanEval+ extra test `[-6,-9]` (base=pass, plus=fail) — exactly what HumanEval+ is designed to catch; gemma handled the negative case. Magnitude matches published: the Qwen3.6 family scores ~90.2% HumanEval+ pass@1 on full EvalPlus (35B-A3B sibling, EvalPlus leaderboard issue #299). The eval discriminates correct vs subtly-buggy code (Qwen fail vs gemma pass on the same problem). Both archs are strong on easy coding (~90–100%); they do NOT separate at the light tier — differentiation is expected at mid (LCB per-difficulty) / heavy (agentic).

### Qwen3.6-27B-OptiQ-4bit light — swap-overlap provenance (2026-06-25)

During this run, a second 29GB model (gemma-4-31B-it-qat-6bit) was accidentally downloaded + briefly started on M5, co-resident with the live Qwen worker (~08:27) → a soft `memory.pressure.warn` (ram_available 16.2GB) + ~1.6GB swap; one in-flight item was swap-slowed. Verdict: **NOT tainted.** The worker never crashed/restarted (etime continuous), no allocation failure occurred (soft WARNING only), and swap is byte-identical on restore (deterministic compute → tokens unchanged, only latency). Confirmed empirically: HE+ and MBPP+ converged 100%, and the single AIME non-convergence (`aime25-14`) is a model-intrinsic hard item that also loops for gemma-31b-6bit and the distill — not swap-induced. A swap/memory event taints SPEED/latency/memory measurements, never QUALITY (pass@1/convergence).

### Temperature ladder — gemma-4-26B-A4B-it-OptiQ-4bit LCB (2026-06-25)

First application of the AGENTS.md temperature-ladder recipe (OFAT `--temp` at fixed 32768 budget headroom, same 15 items). Result: **lowering temperature makes convergence WORSE, not better** — the curve is hump-shaped and production temp 0.7 is near its peak.

| temp | converged | budget-hit | median thinking tokens |
|---|---|---|---|
| 0.7 | 8/15 (53%) | 7 | 14,146 |
| 0.5 | 2/9 (22%) | 7 | 33,497 (> budget) |

Dropping 0.7→0.5 doubled the reasoning length and halved convergence (large effect, decision-grade despite n=9). Likely mechanism: the reasoning-exit token isn't the argmax, so lower/greedier temp keeps extending the most-probable "more reasoning" continuation and rarely samples the exit. temp 0.3 was NOT run (the descent was counterproductive). **DECISION: operate this model at production temp 0.7** (recorded LCB pass@1 80% E100/M86/H60 @ production budget). Combined with the budget finding (16384→32768 didn't help — see the THINKING-BUDGET rule in AGENTS.md), gemma-MoE's hard-LCB over-reasoning is INTRINSIC — not tunable via temp-down or budget-up. Raw rungs archived: `livecodebench.t07.jsonl` (15), `.t05.jsonl` (10, partial).

### Qwen3.6-27B-MLX-8bit light — DNF (non-convergence: MEANDERING) (2026-06-25)

**STOPPED at 16/25, marked DNF/INVALID** for non-convergence. Multiple items saturate the
81920 thinking budget generating ~82K-token traces — including an EASY coding item
(`Mbpp/596` ct=81,946) and `aime24-89` (ct=82,763) — at ~12 tok/s that's ~2h/item, projecting
~10–30h for the light tier alone. The big items HIT the budget (ct ≥ 81,920) → non-converged.

**Non-convergence TYPE = MEANDERING (over-exploration), NOT degenerate repetition.** Confirmed
via a capped-budget probe (aime24-72): the reasoning is coherent step-by-step math with
8-gram/20-gram uniqueness ≈1.00 (no verbatim loops, only one repeated expression) and
backtracking markers ("wait"×7, "actually"×3) — it re-derives and re-checks at length without
concluding. Consistent with the saved final answers being coherent (boxed) despite the
budget-saturated think. This is the `meandering` non-convergence class (vs gemma's temp-1.0
`degenerate-repetition`).

Anomalous vs the OTHER Qwen quants (OptiQ-4bit + UD-6bit converge cleanly), so suspect the
unsloth 8bit checkpoint (template/thinking handling) or genuine 8bit verbosity — not the other
Qwen results. **DEPRIORITIZED** (heaviest quant; 8-bit weights don't fit ≤46GB@256K anyway).
Harness gap surfaced: the `generate` path persists only the post-`</think>` answer, not the
thinking text, so the DNF *type* required a live probe — capture thinking for future DNF triage.

### Provenance

Grading detail and the stale-router / temp-1.0 root cause live in git history (commits through acad470) and `AGENTS.md`.

# Perf + Thinking-Convergence Plan (2026-06-21)

**Context.** Mid bake-off (Qwen3.6-27B-UD-MLX-6bit reasoner vs gemma-4-26B-A4B-it-QAT-MLX-4bit daily). Candidates are locked from a speed/quality standpoint, so optimizing *them* now is not premature — and the lossless levers will speed up the remaining (slow) measurement runs. This plan folds in the prior perf plans (TQ kernel work, unified fused-kernel spec, MTP, EpiCache/OSCAR, NA) and bakes in the operational constraints below.

## Operating constraints (binding for every experiment here)

1. **Realistic config only.** Thinking **enabled**; all generation params come from `opencode_config/opencode.json` (≡ `bench/model_params.py:params_for`, verified identical) + the spawn params in `main_models.yaml` (`kv_quant_scheme`, `kv_bits`, `prefill_step_size`, `draft_*`). No stripped-down configs. When an experiment varies one param (e.g. a temp ladder), everything else stays at the realistic value.
2. **Thinking must converge — budget is a backstop, never the fix.** The model must close its thinking and emit EOS *on its own*. Hitting `thinking_budget` (Qwen 49152 / gemma 16384) is a **failure signal**, not a solution. We never "fix" rambling by lowering the cap; the cap stays high as insurance only.
3. **Two machines, one model each.** M2max (local) + M5max (remote, ~7× faster). Parallelize by assigning whole models to a box (gemma-side on one, Qwen-side on the other); never load two models on one machine.
4. **Lossless now; lossy as isolated perf/quality evals.** Lossless = changes speed/memory, not token outputs (suffix decode, MTP/spec-decode, GQA tile-reuse, chunked prefill, pool caps, cache-eviction bug fixes). Lossy = changes outputs (KV-bit reduction, EpiCache/OSCAR token eviction, weight-quant level) → each measured in isolation against the ≤5% quality-neutral bar.

---

## Workstream 0 — Thinking convergence (PREREQUISITE, top priority)

**Why first:** non-convergence (rambling to the cap, no EOS) contaminates *both* axes — quality (the model is lost, not reasoning) and speed (16–32K tokens/turn). Until it's resolved, every thinking-on measurement is suspect, and a daily-driver that rambles 20K tokens/turn is unusable regardless of accuracy. Observed: gemma-QAT-4bit hits `finish=length` on aggregation@8K at temp 0.1/0.3/0.5/0.7 (does not converge). User reports a *different quant* did not ramble → prime hypothesis is **quant-specific**.

- **0a. gemma quant-convergence ladder (do first, M2).** Sweep the available gemma-A4B quants — **QAT-4bit, OptiQ-4bit, vanilla-4bit, 8bit** — at identical realistic params (temp 0.7, thinking on, full param set), on (i) aggregation@8K and (ii) a real opencode-style coding prompt. Metric: **EOS rate (`finish=stop`)**, completion-length distribution, accuracy. Goal: find a quant that **converges AND fits 256K@≤46GB** (i.e. a *4-bit*). This tests "is rambling a 4-bit defect, or QAT-specific, or all-quant?" (candidate research flags 4-bit weights with large long-ctx loss vs ~0.8% at 8-bit — confirm). Established baseline: QAT-4bit does **not** converge (aggregation@8K `finish=length` at temp 0.1/0.3/0.5; accuracy rose 0.47→0.67→0.80 with temp but never EOS).
- **0b. Decision rule (user-set): a 4-bit that won't converge is useless.** So:
  - If **another 4-bit (OptiQ/vanilla) converges** → adopt it as the gemma daily-driver candidate (keeps the 256K@46GB fit). Re-pull a 6-bit / different family from HF if needed (none cached; no A4B-UD/6-bit exists locally).
  - If **only 8-bit converges** → note the tension: 8-bit (~26GB weights) **does not fit 256K@46GB**, so gemma loses its core advantage (256K fit). Then gemma is either a **<256K daily-driver** (8-bit, lower context ceiling) or gets **down-ranked**, leaving Qwen (now 256K-viable once the OOM is fixed, retrieval 1.0→256K confirmed) as the likely sole pick.
  - If **nothing converges** → 0c.
- **0c. Root-cause sweep (if convergence is not quant-fixable):** systematic-debugging on the convergence path — the fork's thinking-format registry / `<think>` close-tag + EOS handling, sampling levers beyond temp (`min_p`, `presence/repetition_penalty`, `top_k`), and the system/prompt. (Note the README "2048 max_tokens fallback → mid-thought truncation" trap — confirm the harness sends a real `max_tokens`.)
- **0d. Confirm Qwen converges** at realistic params on M5 (reasoning runs report `finish_reason`; if Qwen also bounces off 49152 it's a shared mechanism, not just gemma).

**Exit:** a config where each *retained* candidate **closes thinking on its own** (median completion well under budget, high EOS rate) at realistic params — *then* the measurement campaign is valid. Budget stays high as backstop only.

---

## Workstream 1 — Lossless perf fixes (NOW, in `../mlx-vlm` / `../mlx-serve` parent forks)

| # | Fix | Mechanism | Effort | Verify | Box |
|---|---|---|---|---|---|
| **L1** | **Prefill-step-size threading** | `--prefill-step-size 512` sizes the `set_cache_limit` pool cap (~9 GB) but the server never threads it into generation → runtime uses the hardcoded **2048** → per-chunk QK^T scratch is **4× the budgeted pool** → long-ctx memory-pressure OOM. Thread `get_prefill_step_size()` into the cached-path `gen_kwargs` + the `BatchGenerator` construction. | S | clean A/B (L3) | code; verify M5 |
| **L2** | **Memory-aware session-cache eviction** | Multi-session KV cache is supposed to LRU-evict under memory pressure; it apparently accumulated across the sequential ladder to OOM. Investigate whether the eviction trigger fires for the anon-session path + threshold; fix so it sheds before critical. (Right fix = make eviction work, not disable caching.) | M | re-run sequential ladder, watch resident mem shed | code; verify M5 |
| **L3** | **Clean OOM root-cause A/B** | Fresh router, *just* 192K/256K (no lower-rung accumulation), suffix **ON**, ± L1 ± L2 → pinpoint the true trigger (prefill-step overshoot vs eviction failure vs suffix) and confirm suffix can stay on. Replaces the earlier confounded A/B. | S | — | M5 |
| **L4** | **GQA tile-reuse (decode)** | Spike C: load each kv-head K/V tile once into threadgroup mem, serve all R=6 query-heads → up to **1.6× @200K decode**, lossless, "highest-value Apple-Silicon speed lever found"; partly in the 2-pass kernel. Verify it's active for Qwen decode; finish/enable if not. | M | needle PASS + decode tok/s | code; verify M5 |
| **L5** | **MTP self-speculation drafter — IN SCOPE (user: chase it).** | `Qwen3.6-27B-MTP-{5,4}bit` as draft + UD-6bit target, `draft_kind=mtp`, spec-verified → claimed **~1.4–2.2× novel decode**, lossless; the only novel-decode lever for dense Qwen. Steps: (1) **download the MTP drafter** (`mlx-community/Qwen3.6-27B-MTP-5bit`, fall back `-4bit` — *not cached on either box*); (2) wire `draft_kind=mtp` for the VL model with GatedDeltaNet recurrent-state capture/rollback on reject (suffix needed a v1.1 fix for this — mtp likely too); (3) confirm drafter footprint is small vs the 256K budget. If a target-side MTP head is required, OptiQ-4bit retains it (29 `mtp.*` keys) while UD-6bit's was stripped — but prefer the separate drafter checkpoint. | L | needle PASS (lossless) + decode tok/s + footprint | code; verify M5 |

**Explicitly NOT now (prior decisions, lossless but no payoff):** TQ fused-MSE prefill kernel (op-level win but 16K end-to-end *tie* + 4 GB + OOM risk; GatedDeltaNet+MLP dominate prefill), TQ decode-compute rewrite (gate-failed: decode is a gather, not a matmul — irreducible), unified fused-kernel big rewrite ("config-level wins are what matter"), Neural-Accelerator/Metal4 TensorOps (dispatch never selects them; prefill-only; workload front-loads prefill → lowest ROI; re-test on a future mlx).

**Lossless tuning (memory↔speed, no quality change):** smaller `prefill_step_size` to pull Qwen 256K MLX-peak from ~53 GB under 46 GB — measure peak + prefill tok/s (not a quality eval).

---

## Workstream 2 — Lossy perf improvements (PLAN NOW, run as targeted perf/quality OFAT evals)

Each runs in **isolation** at realistic config, reporting **perf gain vs quality delta** against the ≤5% quality-neutral bar (per-axis: tighter on correctness/recall, looser on style), and **logging the bottleneck/mechanism** (compute vs bandwidth, which memory pool) for B200 transfer.

| # | Lever | Hypothesis | Measure |
|---|---|---|---|
| **Y1** | KV-bit / TQ-mode (MSE-4 vs Prod-3 vs lower), per context band | MSE-4 is the quality leader that fits 200K; Prod-3 only for >256K extreme memory | decode tok/s + MLX-peak vs the quality axes; confirm the per-context guidance |
| **Y2** | **EpiCache** (token eviction) | Fewer *tokens* (not fewer bits) — consistent with the compute-bound decode finding; long-ctx decode + memory lever | quality delta vs decode speedup/memory at long ctx |
| **Y3** | OSCAR (sub-4-bit KV) | Likely wrong for single-user Apple (memory not binding at 4-bit; its win is GPU/bandwidth and inverts here) — but measure; calibration-aware rotation idea worth parking | quality vs decode/memory |
| **Y4** | Weight-quant level (4 vs 6 vs 8-bit) | Ties to W0: if 4-bit degrades convergence/quality, this quantifies the cost vs the memory/speed it buys | convergence + quality + memory + tok/s |

(EpiCache/OSCAR are named-only in prior docs — no mechanism/numbers yet; Y2/Y3 include a scoping step.)

---

## Execution & parallelization

- **Code-only work (L1/L2/L4/L5 fork edits)** needs no GPU → author anytime in the parent forks; **propose each diff before applying** (edit-parent-forks rule), then one short verification run per fix slotted onto a free box. Deploy to M5 via submodule/reinstall for its verification.
- **Box assignment (1 model each, parallel):** gemma-side experiments (W0 convergence A/B, gemma perf/verify) on **M2**; Qwen-side (Qwen convergence check, L3 clean A/B, Qwen perf/verify) on **M5**. Both candidates are cached on both boxes, so either can host either if one is idle.
- **Sequencing:** W0 convergence ladder + L1/L2/L3 (unblock 256K + valid thinking) **first** → L4 (GQA reuse) → **L5 (MTP — in scope)** → **lock the final config** (converged thinking + lossless levers) → run the measurement campaign (reasoning reruns + coding axes) on the locked config → then **Y1 + Y2** lossy OFAT evals as Phase-2 deltas (Y3/Y4 later).
- **Retrieval (no-think) already banked** and is unaffected by all of the above except the Qwen 192K/256K rungs, which L1–L3 will re-enable and re-measure.

## Decisions (resolved 2026-06-21)
1. **MTP (L5): chase it now** — in scope, not deferred (download the drafter, validate GDN rollback).
2. **gemma convergence/quant:** a 4-bit that won't converge is **useless** → if another 4-bit (OptiQ/vanilla) converges, adopt it (keeps 256K fit); else if only 8-bit converges, gemma becomes a <256K driver or is down-ranked (8-bit doesn't fit 256K@46GB) — pursue a 6-bit/other family from HF only if needed.
3. **Lossy depth: Y1 + Y2 now** (KV-bit/TQ-mode + EpiCache); Y3/Y4 later.

---

## Current state (handoff snapshot, 2026-06-21)

**Done / banked:**
- **Retrieval (no-think, `--thinking-budget 0 --max-tokens 256`)** — methodology fixed (full-thinking was infeasible + thinking-contaminated; substring scorer is robust to it). Curves: **gemma-QAT-4bit weak** (0.76/0.56/0.40/0.04/0.16/0.12 over 8–256K, eff_ctx **None**); **Qwen-6bit strong** (1.0 to 128K). Qwen 192K/256K on the production-config ladder **OOM-crashed**, but a clean suffix-off probe got **192K 5/5 and 256K 5/5** → Qwen retrieval ceiling is **256K** (OOM was infra, not capability). Re-run Qwen 192K/256K into the curve once L1–L3 land.
- **Convergence finding:** gemma-QAT-4bit does **not** converge on aggregation@8K (rambles to `finish=length` at temp 0.1/0.3/0.5). This **invalidates the reasoning numbers below** and is the W0 trigger.
- **OOM root-cause:** NOT suffix bypassing chunking (the `chunked_prefill_policy` + `draft_kind=suffix` path is correct). Real cause = **prefill-step-size mismatch** (runtime 2048 vs pool budgeted for 512 → 4× scratch overshoot) **+ probable session-cache eviction failure** (accumulation across the sequential ladder). See L1/L2.

**Invalid / must re-run (at converged config):** gemma reasoning — aggregation 0.48 (4-bit) / 0.56 (8-bit) and latent 0.60 (4-bit), all at temp 0.7 with rambling. Qwen reasoning not yet run.

**Not started:** IFEval, LiveCodeBench, BFCL, Aider, SWE-Verified-40, judge panel; all of W1 (L1–L5) and W2.

**Machine state at handoff:** M2 router up on :8000 (idle, model unloaded). **M5 router DOWN** (killed during cleanup — bring it up per the recipe). M5 `.venv-bench` grading venv built (base reqs + lcb_runner). Transient suffix-off test-router (was :8001) and its `test_qwen_nosuffix.yaml` are gone/stale.

---

## Operational appendix (drive-ready)

**Boxes.** M2max = local (this repo: `$STACK_REPO`). M5max = `ssh $REMOTE_HOST` (repo `$REMOTE_REPO`, user `$REMOTE_USER`, ~7× faster). **M5 non-interactive ssh has a bare PATH** — every remote command must start with `export PATH=/opt/homebrew/bin:$HOME/.local/bin:$PATH`. Both have the candidates cached.

**Parent forks (edit here, NOT `src/*` submodules):** `../mlx-vlm` and `.../mlx-serve`. Deployed code runs from each repo's `src/mlx-vlm` submodule + the repo `.venv`; after a fork fix, deploy to the box for verification. Both fork and M5 submodule are at mlx-vlm `7009a3f` (clean) for the functions in play.

**Serving recipe (per box).** `cd <repo> && set -a; . ./.env; set +a; MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start >logs/main_model.log 2>&1 </dev/null &` → router on **:8000** (`/health`, `/v1/models/load`, `/v1/models/unload`). One model resident; unload + `pkill -f bench.run_*` between models. Watch `logs/main_model.log` completion lines for live per-request progress (the bench runners print per-rung only at the end).

**Realistic params (binding).** `bench/model_params.py:params_for(model)` ≡ `opencode_config/opencode.json` (verified identical): Qwen temp 0.7/top_p 0.95/top_k 20/min_p 0.03/presence_penalty 0.3/max_tokens 81920/enable_thinking true/thinking_budget 49152; gemma temp 0.7/top_p 0.95/top_k 64/repetition_penalty 1.08/max_tokens 32768/enable_thinking true/thinking_budget 16384. `main_models.yaml` carries spawn params: Qwen `kv_quant_scheme: turboquant, kv_bits: 4, prefill_step_size: 512, draft_kind: suffix`. Vary only the param under test; keep the rest realistic.

**L1 fix (prefill-step threading) — exact location.** `mlx_vlm/server/generation.py`: `_process_cached_request` builds `gen_kwargs` (~line 1299) without `prefill_step_size`; and the `BatchGenerator(...)` construction (~line 1726) omits it → both fall back to `DEFAULT_PREFILL_STEP_SIZE = 2048` (`generate/ar.py:194`). Fix = pass `get_prefill_step_size()` (already defined `server/generation.py:119`) into both. Regression test mirrors `test_generate.py` chunked-prefill tests. (Diff drafted in session; re-derive/confirm against the fork before applying.)

**Monitoring pattern.** Launch long runs detached on the box (`nohup … </dev/null &`), then a **local background Bash poller** (`run_in_background: true`; not subject to the 10-min foreground cap) that checks for the result file / `pgrep` liveness and re-invokes on done/dead. Foreground `sleep` is blocked — use a poll loop or `Monitor`.

**Probe building blocks (standalone scripts, no harness edit):** `bench.aggregation.build_cwe(target_tokens, cpt, k=5, seed=…)` + `score_cwe`; `bench.retrieval.build_context/make_question/hits`; `bench.latent.*`; `bench.driver.MlxServeDriver().complete(model, msgs, params)` returns `content/reasoning/completion_tokens/finish_reason/wall_s/decode_tps/...`. `MLX_SERVE_BASE` env overrides the router URL. Run with `PYTHONPATH=. <repo>/.venv/bin/python …` from `benchmark/` (cpt≈4.6).

**Suffix/prefill investigation artifacts:** the L1 diagnosis + draft diff and the convergence data are in this session's transcript; the prior digest covers all perf techniques + statuses.

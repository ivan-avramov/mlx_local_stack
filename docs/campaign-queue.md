# Campaign work queue (durable)

The comprehensive, durable backlog for the 256K agentic-coding selection campaign — a
candidate × axis status matrix feeding a per-box worklist, so a freed box always pulls its
next item (never "TBD"). Companion docs: results + rankings in `docs/campaign-results.md`
(the AGGREGATE record); process/recipes (sampling profiles, temperature-ladder, budget
mechanics, convergence rule, full-model-name rule) in `AGENTS.md`. **Keep this file current.**

**Box-split note:** each box has its OWN `benchmark/results/` — campaign state is scattered
across M2 + M5; `campaign-results.md` is the single aggregated truth. Two KV configs are
tracked per model: production-KV (4-bit, daily-driver) and the `-kv16` (bf16-KV) ceiling variant.

**Durability:** SURVIVES a reboot — this file + per-box `benchmark/results/*.jsonl` +
`.manifest.json` (generation RESUMES via done_ids; `--clean-stale` reconciles config). DOES NOT
survive — the nohup'd drivers + monitors. After a reboot, relaunch each `[RUNNING]` driver per
**Reboot recovery**. (Full registry names only — per the AGENTS.md rule; no shorthands.)

Last updated: 2026-06-26.

## Status matrix (✓ done · ~ running · ◻ pending · ⚠ stale/blocked · – n/a)

| candidate (full name) | arch | capacity | light | LCB (prod-KV) | notes |
|---|---|---|---|---|---|
| gemma-4-26B-A4B-it-OptiQ-4bit | MoE | ✓ | ✓ | ✓ (temp-ladder → keep t0.7) | lead MoE 4-bit |
| gemma-4-26b-a4b-it-8bit | MoE | ✓ | ✓ | ✓ | +kv16 LCB ✓ |
| gemma-4-26b-a4b-it-4bit | MoE | ◻ | ✓ | ✓ INVALID (over-reasons) | dominated |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | MoE | ✓ | ✓ | ✓ INVALID (loop-prone) | dominated |
| gemma-4-31b-it-6bit | dense | ◻ | ✓ | ✓ **86.7%** (conv 12/15) | +kv16 LCB ✓; beats MoE |
| gemma-4-31b-it-UD-MLX-4bit | dense | ✓ | ✓ | ✓ **86.7%** (conv 14/15) | cleanest LCB conv; beats MoE |
| gemma-4-31B-it-qat-6bit | dense | ◻ | ✓ **AIME 100%/100%conv** | ✓ 80% (conv 14/15) | **convergence + reasoning leader** |
| Qwen3.6-27B-UD-MLX-6bit | dense | ✓ | ✓ | ⚠ DNF-MEANDER (item1 ct82507>81920, ~114min/item) | 3rd Qwen-arch LCB DNF; +kv16 LCB ✓ |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | MoE-distill | ✓ | ✓ | ⚠ DNF-MEANDER (median 82,855>bud) | |
| Qwen3.6-27B-OptiQ-4bit | MoE | ✓ | ✓ | ✓ | only prod-KV Qwen LCB done |
| Qwen3.6-27B-MLX-8bit | MoE | ◻ | ⚠ DNF (meander) | ◻ | DEPRIORITIZED; +kv16 LCB ✓ |
| Ornith-1.0-35B-mlx-uniform-4bit | MoE-hybrid | ✓ **256K@32.4GB, ret1.00** | ✓ (he90/mbpp80 VALID; aime 1 budget-hit) | ~ RUNNING @t0.6 | GATE PASS (first to clear true 256K); converges @t0.6; fast 37-72tok/s |

**Higher tiers — `◻` PENDING for ALL candidates** (none run): math500, IFEval (⚠ blocked), GPQA,
BFCL (tool-calling), Aider polyglot, SWE-Verified-40 (agentic), judge panel.

## Per-box worklist (pull next from here)

### M5 (256K-capable, quiet box)
1. **[DONE]** Qwen3.6-27B-MLX-8bit — light: **DNF/DEPRIORITIZED** (MEANDERING non-convergence,
   82K-token budget-saturating traces incl. easy coding; suspect the unsloth 8bit checkpoint;
   8-bit won't fit ≤46GB@256K). See campaign-results.md.
2. **[DONE]** gemma-4-31B-it-qat-6bit — light: STANDOUT (HE+ 100% / MBPP+ 80% / AIME 100%, all
   100% convergence, all VALID). Graded + recorded.
3. **[DONE]** M5 LCB sweep:
   a. gemma-4-31B-it-qat-6bit LCB ✓ — 80% (E100/M86/H60), conv 14/15 (cleanest dense conv).
   b. Qwen3.6-27B-Opus-Distill-OptiQ-4bit LCB ⚠ **DNF-MEANDER** (stopped at 8/15; median 82,855 >
      budget) — same pathology as Qwen3.6-27B-MLX-8bit.
4. **[DONE — DNF]** Qwen3.6-27B-UD-MLX-6bit LCB @ qwen official — **DNF-MEANDER** (2026-06-26):
   item 1 (id 3496) `finish=stop` but `ct=82507 > 81920` budget = NON-CONVERGED, ~114 min/item,
   driver ETA ~26h → cut at N=1 (strong priors: prior run 11–17h ETA + 8bit + distill both DNF'd).
   3rd Qwen3.6-27B-arch LCB DNF. Recorded in campaign-results.md.
5. **[RUNNING] math500 (N=30) on gemma-4-31B-it-qat-6bit** @ production (launched 2026-06-26 to
   refill M5 after the LCB cut) — completes the reasoning axis across all 3 dense gemmas
   (6bit + UD-4bit on M2). qat-6bit is the convergence leader → expect fast clean convergence.
   Grade on completion; record + append.
6. **[CONVERTED + VALIDATED + light tier RUNNING @ t0.6] deepreinforce-ai/Ornith-1.0-35B** (uniform-4bit).
   - **2026-06-26 STATUS:** converted (uniform-4bit, ~19GB, 4.649bpw, M5-local registry entry, uncommitted)
     + smoke-loaded (all keys map) + canary-generated coherent code. Decode is FAST: **69 tok/s** (linear-attn
     payoff, ~5-7x the dense gemmas). Light tier (he+/mbpp+/aime) RUNNING @ official **temp 0.6** (pid via
     logs/ornith_light_t06.log), launched DIRECTLY (run.py generate, --clean-stale) — see CANARY note below.
   - **CONVERGENCE — the open question:** Ornith inherits the qwen3_5_moe meander. Preflight canary @ PRODUCTION
     **temp 0.7** MEANDERED on a trivial is_palindrome: finish=stop but ct=49221 > 49152 budget = NON-CONVERGED
     (cousin Qwen3.6-27B-UD-MLX-6bit converged the same canary in 1941 tok @ 0.7). BUT manual canary @ **temp 0.6**
     converged is_prime in 1369 tok → sharp temp knee. Running light tier @ 0.6 to test convergence on real benches;
     if it meanders @ 0.6 too → temp-ladder (0.5/0.3) or DNF. Watcher reports first-items convergence.
   - **HARNESS ISSUE (preflight-profile mismatch):** preflight.py run_canary HARDCODES production params
     (temp 0.7), ignoring the run's :official profile → false-fails qwen-arch models we eval @ 0.6. FIX (TDD):
     thread the sampling profile through preflight.sh -> preflight.py:run_canary. Queued.
   - **LOADER FIX SHIPPED 2026-06-26** (fork f0d50c9, stack submodule bump af992b6, synced to M5):
     `qwen3_5_moe.sanitize` now tolerates the UNFUSED per-expert layout (stacks
     `experts.{e}.{proj}.weight` → `switch_mlp.{proj}.weight`); fused Qwen3.6-VL path preserved.
     TDD: `mlx_vlm/tests/test_qwen3_5_moe_sanitize.py` (both layouts, 24 tests pass). The fork's
     `qwen3_5_moe` already implements the full hybrid arch (GatedDeltaNet `linear_attn` + full-attn,
     MoE with `shared_expert` + router) — this sanitize gap was the only blocker.
   - **NEXT (needs M5 free — currently running math500 on qat-6bit):**
     (i) smoke-load real Ornith via PYTHONPATH, confirm ZERO missing/unexpected keys;
     (ii) `python -m mlx_vlm.convert --hf-path <snap 5df2ed3f> -q --q-bits 4 --mlx-path <out>` (uniform-4bit, ≈27GB);
     (iii) M5-local uncommitted `main_models.yaml` entry (kv_bits 4, max_kv_cache_size, prefill_step_size 512);
     (iv) capacity `mx.get_peak_memory`@256K → retrieval → LCB → BFCL native-FC → SWE-Verified-40.
   - a. [DONE] BF16 → 65G / 16 shards in cache (snapshot 5df2ed3f).
   - b. **ROOT CAUSE (2026-06-26):** NOT a simple prefix issue. Ornith is a **hybrid linear-attention
     MoE** (Qwen3-Next-style): layers use `linear_attn.*` (A_log/conv1d/dt_bias/in_proj_qkv|a|b|z/
     out_proj), MoE = router `mlp.gate` + **256 UNFUSED experts** (`experts.{0..255}.{gate,up,down}_proj.weight`)
     + a **shared expert** (`mlp.shared_expert.*` + `shared_expert_gate`), all under the VL wrapper
     (`model.language_model.*` + `model.visual.*`). config: model_type qwen3_5_moe / text qwen3_5_moe_text,
     40 layers, 256 experts / 8 active, moe_intermediate 512, shared_expert_intermediate 512, tie=False.
   - `mlx_vlm.convert` (right tool, routes through `qwen3_5_moe.sanitize`) FAILED:
     `KeyError: model.language_model.layers.0.mlp.experts.gate_up_proj` — the fork's sanitize expects
     the **fused** Qwen3.6-VL expert layout, Ornith ships **unfused** experts + a shared expert.
   - **FIX (engineering, attended):** patch `../mlx-vlm/.../qwen3_5_moe/qwen3_5_moe.py:sanitize` to
     STACK the 256 unfused `experts.{e}.{proj}.weight` → 3D `switch_mlp.{proj}.weight`, handle the
     `shared_expert` keys, and CONFIRM the fork's `language.py` actually implements the `linear_attn`
     layer (conv1d handling in sanitize suggests yes — verify). Smoke-load via PYTHONPATH before
     converting. Alt route: mlx_lm `qwen3_next` text loader + key-remap (strip `model.language_model.`,
     drop `model.visual.*`). **QAT is NOT possible for us** (training-time).
   - DECISION PENDING: worth the port vs deprioritize? Front-runner (dense gemma-4-31B) is already clear.
   - EVAL (if built): capacity @256K → retrieval → LCB → BFCL native-FC → SWE-Verified-40.
   - MEMORY @256K: uniform-4bit + 4-bit KV ≈ 27GB; uniform-6bit + 4-bit KV ≈ 36–40GB — both fit ≤46GB.
     (OptiQ NOT reachable via `mlx_vlm.convert` — q_modes are affine/mxfp4/nvfp4/mxfp8; OptiQ = separate tool.)

### M2 (local laptop, ≤192K only — co-resident ~22GB)
1. **[DONE]** dense-gemma LCB @ production t0.7: gemma-4-31b-it-6bit **86.7%** (conv 12/15) +
   gemma-4-31b-it-UD-MLX-4bit **86.7%** (conv 14/15) — both BEAT the MoE (80%, H60→H80) with
   cleaner convergence. Graded + recorded.
2. **[DONE]** math500 (N=30) @ production — graded 2026-06-26: gemma-4-31b-it-6bit **83.3% / 100%
   conv / VALID** (median 2000); gemma-4-31b-it-UD-MLX-4bit **83.3% raw but 67% conv / INVALID**
   (over-reasons, median 8165, 10 loops — 4-bit tail-fragility). With gemma-4-31B-it-qat-6bit
   (83.3% / 100% conv / VALID, M5) → all 3 dense gemmas done on math500. Recorded in campaign-results.md.
3. **[NEXT — on M2-idle, ATTENDED first-run]** Aider polyglot SMOKE (`--limit` small) on the dense
   front-runner (gemma-4-31b-it-6bit / UD-4bit), then full Aider → SWE-Verified-40. CORE agentic
   axes, never run — the real "256K agentic coding" test. Box-idle monitor pings M2-IDLE → launch.
4. **[QUEUED]** BFCL native-FC on the lead gemma candidates.

## Backlog (unassigned — priority order)
1. **Finish LCB across ALL candidates** (the differentiator) — partly in the worklists above.
2. **Agentic axes: Aider polyglot + SWE-Verified-40** on LCB survivors — the campaign's CORE; built, never run.
3. **BFCL native-FC** (tool-calling) — built, never run.
4. **Judge panel** (Sonnet+Opus+codex, blind, over execution-PASSING outputs only) — built, never run.
5. **math500 + GPQA** (reasoning) — built, never run.
6. **New candidates to acquire:** Qwen3.6 oMLX-6bit, Qwen3.6-27B-MTP variants.
7. **WATCH-FOR-RELEASE — `deepreinforce-ai/Ornith-1.0-31B` (Dense, Gemma-4-based):** announced in the
   Ornith-1.0 blog/news (family = 9B Dense / **31B Dense (Gemma-4)** / 35B MoE (Qwen-3.5) / 397B MoE),
   but NOT yet on HF as of 2026-06-26 (authoritative API list with token = 35B/9B/397B only; the 31B repo
   404s). HIGH PRIORITY when it lands — it's our converging dense front-runner's base (gemma-4-31B) PLUS
   Ornith's self-scaffolding agentic-coding RL, directly targeting the campaign's open differentiator.
   Re-check HF periodically. (35B MoE = ours, already converted/eval'd. 9B Dense available now but below the
   64GB capability target — low value.)
8. **Effective-context curves** (retrieval-depth + reasoning-depth, kept SEPARATE; retrieval
   partial, reasoning-depth not started) — the ≥0.85 gate.
9. **bf16-KV ("kv16") ceiling sub-study** — kv16 LCB exists for Qwen3.6-27B-MLX-8bit /
   Qwen3.6-27B-UD-MLX-6bit / gemma-4-26b-a4b-it-8bit / gemma-4-31b-it-6bit; extend + compare vs
   production-KV per the quality-first plan.

## Blocked
- **IFEval**: `datasets` load fails "Feature type 'List' not found" (version incompatibility) — fix
  before the instruction-following axis runs; the sweep currently skips it (acc:null, no crash).

## Gating policy
- Breadth-first: capacity → light → LCB → (survivors) reasoning/tool → agentic → judge.
- **NO pruning on partial results** — cuts decided only across the full suite.
- Emerging signal: DENSE gemma-4 converges where the MoE loops (gemma-4-31B-it-qat-6bit leads);
  the MoE's edge is decode speed. Pending the LCB-differentiator completion + agentic axes.
- Gates: ≤46GB MLX-peak @256K (≤56GB browser-closed, metric = `mx.get_peak_memory`); M2 ≤192K;
  ONE resident model per box; judge over execution-PASSING outputs only; two eff-ctx curves separate.

## Reboot recovery
1. Restart the router (per-box recipe in AGENTS.md): `MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start …` → :8000.
2. For each `[RUNNING]` item, relaunch its driver (`lightsweep.sh`/`tempsweep.sh`, same args) — it resumes from disk via done_ids / `--clean-stale`.
3. The deferred wrappers + box-idle/per-model monitors are unreliable across M5 IP changes — drive M5 MANUALLY against this worklist; find M5 by ssh-scanning the subnet (`nc -G 3`, not `-G 1`).
4. Sanity-check with `benchmark/preflight.sh` before trusting a resumed run.

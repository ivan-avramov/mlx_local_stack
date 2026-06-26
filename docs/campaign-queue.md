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

Last updated: 2026-06-25.

## Status matrix (✓ done · ~ running · ◻ pending · ⚠ stale/blocked · – n/a)

| candidate (full name) | arch | capacity | light | LCB (prod-KV) | notes |
|---|---|---|---|---|---|
| gemma-4-26B-A4B-it-OptiQ-4bit | MoE | ✓ | ✓ | ✓ (temp-ladder → keep t0.7) | lead MoE 4-bit |
| gemma-4-26b-a4b-it-8bit | MoE | ✓ | ✓ | ✓ | +kv16 LCB ✓ |
| gemma-4-26b-a4b-it-4bit | MoE | ◻ | ✓ | ✓ INVALID (over-reasons) | dominated |
| gemma-4-26B-A4B-it-QAT-MLX-4bit | MoE | ✓ | ✓ | ✓ INVALID (loop-prone) | dominated |
| gemma-4-31b-it-6bit | dense | ◻ | ✓ | ✓ **86.7%** (conv 12/15) | +kv16 LCB ✓; beats MoE |
| gemma-4-31b-it-UD-MLX-4bit | dense | ✓ | ✓ | ✓ **86.7%** (conv 14/15) | cleanest LCB conv; beats MoE |
| gemma-4-31B-it-qat-6bit | dense | ◻ | ✓ **AIME 100%/100%conv** | ~ (M5 now) | **convergence + reasoning leader** |
| Qwen3.6-27B-UD-MLX-6bit | dense | ✓ | ✓ | ◻ (M5 queued; watch meander) | +kv16 LCB ✓ |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | MoE-distill | ✓ | ✓ | ~ (M5; watch meander) | |
| Qwen3.6-27B-OptiQ-4bit | MoE | ✓ | ✓ | ✓ | only prod-KV Qwen LCB done |
| Qwen3.6-27B-MLX-8bit | MoE | ◻ | ⚠ DNF (meander) | ◻ | DEPRIORITIZED; +kv16 LCB ✓ |
| deepreinforce-ai/Ornith-1.0-35B | MoE | ◻ | ◻ | ◻ | NEW; in PREP (M5) |

**Higher tiers — `◻` PENDING for ALL candidates** (none run): math500, IFEval (⚠ blocked), GPQA,
BFCL (tool-calling), Aider polyglot, SWE-Verified-40 (agentic), judge panel.

## Per-box worklist (pull next from here)

### M5 (256K-capable, quiet box)
1. **[DONE]** Qwen3.6-27B-MLX-8bit — light: **DNF/DEPRIORITIZED** (MEANDERING non-convergence,
   82K-token budget-saturating traces incl. easy coding; suspect the unsloth 8bit checkpoint;
   8-bit won't fit ≤46GB@256K). See campaign-results.md.
2. **[DONE]** gemma-4-31B-it-qat-6bit — light: STANDOUT (HE+ 100% / MBPP+ 80% / AIME 100%, all
   100% convergence, all VALID). Graded + recorded.
3. **[RUNNING]** M5 LCB sweep (`lightsweep.sh`, livecodebench=15), in order:
   a. gemma-4-31B-it-qat-6bit @ production t0.7 (running first — fast, validated)
   b. Qwen3.6-27B-Opus-Distill-OptiQ-4bit @ qwen official — **WATCH for meandering**
   c. Qwen3.6-27B-UD-MLX-6bit @ qwen official — **WATCH for meandering** (unsloth, like the DNF'd 8bit)
   → watch the first few items' token lengths on the Qwen rungs; cut/flag if they saturate the
   81920 budget like Qwen3.6-27B-MLX-8bit did. Apply the temperature-ladder recipe only if a
   model won't converge.
4. **[QUEUED — PREP] deepreinforce-ai/Ornith-1.0-35B** (M5 ONLY @256K; sampling = qwen
   official, temp 0.6). MoE (8-of-256 experts) — **measure its convergence, don't assume the
   dense advantage**.
   - PREP (no MLX build upstream; **QAT is NOT possible for us** — it's training-time, would need
     DeepReinforce to release QAT weights; we do post-training quant only):
     a. [DONE] BF16 → 65G / 16 shards in cache.
     b. [NEXT — M5-free only: RAM] quantize → MLX: **OptiQ 6-bit** (`mlx-optiq`, quality-first
        primary) **+ uniform 4-bit** (`mlx_lm.convert`, memory-safe baseline); record eff-bpw via
        `quant_info`. CAUTION: 65GB BF16 on a 64GB box can OOM unless the converter streams/mmaps —
        verify first.
     c. verify the `qwen3_5_moe` loader (256-expert gather; `Qwen3_5MoeForConditionalGeneration`
        → confirm loads as text) on a tiny smoke.
     d. M5-local (uncommitted) `main_models.yaml` entry: kv_bits 4, `max_kv_cache_size`,
        `prefill_step_size 512`.
   - EVAL: capacity `mx.get_peak_memory`@256K → retrieval → LCB → BFCL native-FC → SWE-Verified-40.
   - MEMORY @256K (heavy GQA, 2 KV heads → small KV): OptiQ-6bit + 4-bit KV ≈ 36–40GB;
     uniform-4bit + 4-bit KV ≈ 27GB — both fit ≤46GB. 8-bit weights or fp16-KV do NOT.

### M2 (local laptop, ≤192K only — co-resident ~22GB)
1. **[DONE]** dense-gemma LCB @ production t0.7: gemma-4-31b-it-6bit **86.7%** (conv 12/15) +
   gemma-4-31b-it-UD-MLX-4bit **86.7%** (conv 14/15) — both BEAT the MoE (80%, H60→H80) with
   cleaner convergence. Graded + recorded.
2. **[RUNNING]** math500 (N=30) on gemma-4-31b-it-6bit + gemma-4-31b-it-UD-MLX-4bit @ production
   (launched while user away — safe known axis, dense reasons concisely on math). NOTE: the
   LCB-completion poller does NOT watch math500 → grade it on M2-idle.
3. **[QUEUED]** agentic axes on gemma LCB-survivors (≤192K fits): Aider polyglot, then
   SWE-Verified-40 (CORE; built+merged, never run — needs attention for the first run, not unattended).
4. **[QUEUED]** BFCL native-FC on the lead gemma candidates.

## Backlog (unassigned — priority order)
1. **Finish LCB across ALL candidates** (the differentiator) — partly in the worklists above.
2. **Agentic axes: Aider polyglot + SWE-Verified-40** on LCB survivors — the campaign's CORE; built, never run.
3. **BFCL native-FC** (tool-calling) — built, never run.
4. **Judge panel** (Sonnet+Opus+codex, blind, over execution-PASSING outputs only) — built, never run.
5. **math500 + GPQA** (reasoning) — built, never run.
6. **New candidates to acquire:** Ornith (in prep), Qwen3.6 oMLX-6bit, Qwen3.6-27B-MTP variants.
7. **Effective-context curves** (retrieval-depth + reasoning-depth, kept SEPARATE; retrieval
   partial, reasoning-depth not started) — the ≥0.85 gate.
8. **bf16-KV ("kv16") ceiling sub-study** — kv16 LCB exists for Qwen3.6-27B-MLX-8bit /
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

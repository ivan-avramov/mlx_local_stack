# Campaign work queue (durable)

The comprehensive, durable backlog for the 256K agentic-coding selection campaign — a
candidate × axis status matrix feeding a per-box worklist, so a freed box always pulls its
next item (never "TBD"). Companion docs: results + rankings in `docs/campaign-results.md`
(the AGGREGATE record); process/recipes (sampling profiles, temperature-ladder, budget
mechanics, convergence rule) in `AGENTS.md`. **Keep this file current as work moves.**

**Box-split note:** each box has its OWN `benchmark/results/` — the campaign state is
scattered across M2 + M5; `campaign-results.md` is the single aggregated truth. Two KV
configs are tracked per model: production-KV (4-bit, daily-driver) and the `-kv16` (bf16-KV)
quality-ceiling variant.

**Durability:** SURVIVES a reboot — this file + the per-box `benchmark/results/*.jsonl` +
`.manifest.json` (generation RESUMES via done_ids; `--clean-stale` reconciles config). DOES
NOT survive — the nohup'd drivers (`lightsweep.sh`/`tempsweep.sh`/deferred wrappers) +
monitors. After a reboot, relaunch each `[RUNNING]` driver per **Reboot recovery**.

Last updated: 2026-06-25.

## Status matrix (✓ done · ~ running · ◻ pending · ⚠ stale/blocked · – n/a)

| candidate (arch) | capacity | light | LCB (prod-KV) | notes |
|---|---|---|---|---|
| gemma-MoE OptiQ-4bit | ✓ | ✓ | ✓ (+temp-ladder→keep t0.7) | lead MoE 4-bit |
| gemma-MoE 8bit | ✓ | ✓ | ✓ | +kv16 LCB ✓ |
| gemma-MoE vanilla-4bit | ◻ | ✓ | ✓ (INVALID: over-reasons) | dominated by OptiQ |
| gemma-MoE QAT-4bit | ✓ | ✓ | ✓ (INVALID: loop-prone) | dominated |
| gemma-dense 31b-6bit | ◻ | ✓ | ~ (M2 now) | +kv16 LCB ✓ |
| gemma-dense UD-4bit | ✓ | ✓ | ~ (M2 now) | cleanest light convergence |
| gemma-dense qat-6bit | ◻ | ⚠ stale-9→rerun (M5) | ◻ | light rerun queued |
| Qwen UD-6bit | ✓ | ✓ | ◻ (prod) | +kv16 LCB ✓ |
| Qwen distill-OptiQ-4bit | ✓ | ✓ | ◻ | |
| Qwen OptiQ-4bit | ✓ | ✓ | ✓ | only Qwen with prod-KV LCB |
| Qwen MLX-8bit | ◻ | ⚠ DNF (meander) | ◻ | DEPRIORITIZED; +kv16 LCB ✓ |
| **Ornith-1.0-35B** (4bit/OptiQ) | ◻ | ◻ | ◻ | NEW; in PREP (M5) |

**Higher tiers — `◻` PENDING for ALL candidates** (none run yet): math500, IFEval (⚠ blocked),
GPQA, BFCL (tool-calling), Aider polyglot, SWE-Verified-40 (agentic), judge panel.

## Per-box worklist (pull next from here)

### M5 (256K-capable, quiet box)
1. **[DNF/DEPRIORITIZED]** Qwen3.6-27B-MLX-8bit — light stopped at 16/25 (MEANDERING
   non-convergence: 82K-token budget-saturating traces incl. easy coding; ~10–30h). Anomalous vs
   other Qwen quants → suspect the unsloth 8bit checkpoint; 8-bit won't fit ≤46GB@256K anyway.
   See campaign-results.md.
2. **[RUNNING]** gemma-4-31B-it-qat-6bit — light (`lightsweep.sh`, production; preflight +
   `--clean-stale` purges the stale-9 and reruns). NOTE: launched MANUALLY (the deferred wrapper
   was disarmed) — drive M5's next items (Qwen LCB → Ornith) manually on idle.
3. **[QUEUED]** Qwen LCB (the differentiator) — UD-6bit, distill, 8bit at qwen `official` (OptiQ-4bit
   already done). Apply the temperature-ladder recipe only if a model won't converge.
4. **[QUEUED]** gemma-4-31B-it-qat-6bit — LCB (after its light).
5. **[QUEUED — PREP]** Ornith-1.0-35B (`deepreinforce-ai/Ornith-1.0-35B`, M5 ONLY @256K). Sampling =
   qwen coding/official (temp 0.6). Memory @256K: OptiQ-4bit+4-bit KV ≈31–39GB / uniform-4bit+4-bit
   KV ≈27GB (heavy GQA, 2 KV heads → small KV; fits ≤46GB; 8-bit or fp16-KV do NOT).
   - PREP: a.[DONE] BF16 → 65G/16 shards in cache. b.[NEXT, M5-free only] quantize → MLX
     uniform-4bit (`mlx_lm.convert`) + OptiQ-4bit (`mlx-optiq`), `quant_info` eff-bpw — CAUTION:
     65GB BF16 on a 64GB box can OOM unless it streams/mmaps. c. verify `qwen3_5_moe` loader
     (256-expert gather; `ForConditionalGeneration`→loads-as-text) on a smoke. d. M5-local
     `main_models.yaml` entry (uncommitted; kv_bits 4, max_kv_cache_size, prefill_step_size 512).
   - EVAL: capacity `mx.get_peak_memory`@256K → retrieval → LCB → BFCL native-FC → SWE-Verified-40.

### M2 (local laptop, ≤192K only — co-resident ~22GB)
1. **[RUNNING]** dense-gemma LCB: gemma-4-31b-it-6bit, gemma-4-31b-it-UD-MLX-4bit @ production t0.7.
2. **[QUEUED]** agentic axes on gemma LCB-survivors (≤192K fits): Aider polyglot, then SWE-Verified-40.
   (CORE campaign axes — tooling built+merged, never run.)
3. **[QUEUED]** BFCL native-FC + math500 on the lead gemma candidates.

## Backlog (unassigned — priority order)
1. **Finish LCB across ALL candidates** (the differentiator) — partly in the worklists above.
2. **Agentic axes: Aider polyglot + SWE-Verified-40** on LCB survivors — the campaign's CORE; built, never run.
3. **BFCL native-FC** (tool-calling) — built, never run.
4. **Judge panel** (Sonnet+Opus+codex, blind, over execution-PASSING outputs only) — built, never run.
5. **math500 + GPQA** (reasoning) — built, never run.
6. **New candidates to acquire:** Ornith (in prep), **oMLX-6bit** (Qwen), **Qwen3.6-27B-MTP** variants.
7. **Effective-context curves** (retrieval-depth + reasoning-depth, kept SEPARATE; retrieval partial,
   reasoning-depth not started) — the ≥0.85 gate.
8. **bf16-KV ("kv16") ceiling sub-study** — kv16 LCB exists for Qwen-8bit/UD-6bit + gemma-8bit/31b-6bit;
   extend + compare vs production-KV per the quality-first plan.

## Blocked
- **IFEval**: `datasets` load fails "Feature type 'List' not found" (version incompatibility) — fix
  before the instruction-following axis runs; the sweep currently skips it (acc:null, no crash).

## Gating policy
- Breadth-first: capacity → light → LCB → (survivors) reasoning/tool → agentic → judge.
- **NO pruning on partial results** — cuts decided only across the full suite (vanilla/QAT MoE LCB
  are weak but stay in the record).
- Gates: ≤46GB MLX-peak @256K (≤56GB browser-closed, metric = `mx.get_peak_memory`); M2 ≤192K;
  ONE resident model per box; judge over execution-PASSING outputs only; two eff-ctx curves separate.

## Reboot recovery
1. Restart the router (per-box recipe in AGENTS.md): `MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start …` → :8000.
2. For each `[RUNNING]` item, relaunch its driver (`lightsweep.sh`/`tempsweep.sh`, same args) — it resumes from disk via done_ids / `--clean-stale`.
3. Re-arm deferred wrappers (e.g. qat-6bit "wait on PID" — repoint at the new driver PID) + the box-idle / per-model monitors.
4. Sanity-check with `benchmark/preflight.sh` before trusting a resumed run.

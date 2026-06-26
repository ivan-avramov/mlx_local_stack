# Campaign work queue (durable)

Live worklist for the 256K agentic-coding selection campaign. **This file is the durable
queue — keep it current as work moves.** Companion docs: results + rankings live in
`docs/campaign-results.md`; the process/recipes (sampling profiles, temperature-ladder,
budget mechanics, convergence rule) live in `AGENTS.md`.

**Durability / what survives a reboot:**
- SURVIVES: this file, the per-item result jsonls + `.manifest.json` under `benchmark/results/`
  (generation RESUMES via done_ids; provenance `--clean-stale` reconciles config changes).
- DOES NOT survive: the nohup'd run drivers (`lightsweep.sh` / `tempsweep.sh` / deferred
  wrappers) and the background monitors — these are process state. After a reboot, relaunch
  the driver for each `[RUNNING]` item (it resumes from disk) per **Reboot recovery** below.

Last updated: 2026-06-25.

## M5 (remote box, `$REMOTE_HOST` / `$REMOTE_USER` / `$REMOTE_REPO`; 256K-capable, quiet box)

1. **[RUNNING] Qwen3.6-27B-MLX-8bit — light** (humanevalplus/mbppplus/aime, qwen `official`).
   Driver: `lightsweep.sh`. Grade he+/mbpp+ via docker evalplus, aime exact-match.
2. **[QUEUED] gemma-4-31B-it-qat-6bit — light.** Deferred wrapper waits on the Qwen driver
   PID, then preflight + light `--clean-stale` (purges the 9 stale pre-failure items). The
   earlier load-503 was an incomplete download — fixed by manual re-download (29GB/6 shards).
3. **[QUEUED — blocked on PREP] Ornith-1.0-35B** (`deepreinforce-ai/Ornith-1.0-35B`).
   Qwen3.5-MoE (`qwen3_5_moe`, 40L, 2 KV heads, 256 experts/8 active), purpose-built for
   agentic coding, 256K native, SWE-Verified 75.6, tool-calling `qwen3_xml`, MIT. Sampling =
   our qwen `coding`/official profile (temp 0.6, top_p 0.95). **M5 ONLY** (256K).
   - PREP (no MLX build exists — GGUF only upstream):
     a. download BF16 (~70GB) to M5 (559GB free, ample).
     b. quantize → MLX: **uniform-4bit** (`mlx_lm.convert -q`, ~17.5GB, memory-safe baseline)
        AND **OptiQ-4bit** (`mlx-optiq`, quality); record eff-bpw via `quant_info`.
     c. verify loader for `qwen3_5_moe` / `Qwen3_5MoeForConditionalGeneration` (256-expert
        gather; `ForConditionalGeneration` → confirm loads as text) on a tiny smoke.
     d. add M5-local (uncommitted) `main_models.yaml` entry: kv_bits 4, `max_kv_cache_size`,
        `prefill_step_size 512`.
   - EVAL (qwen coding profile): capacity `mx.get_peak_memory` @256K → retrieval → LCB
     (apply the temperature-ladder recipe if it won't converge) → BFCL native-FC →
     SWE-Verified-40 (the axis it's built for).
   - MEMORY @256K (heavy GQA, 2 KV heads → small KV): OptiQ-4bit + 4-bit KV ≈ 31–39GB,
     uniform-4bit + 4-bit KV ≈ 27GB — both fit the ≤46GB gate. 8-bit weights or fp16-KV do NOT.

## M2 (local laptop, co-resident with the AI session ~22GB → ≤192K only)

1. **[RUNNING] gemma-4-26B-A4B-it-OptiQ-4bit — temperature-ladder @coding LCB.**
   Driver: `tempsweep.sh`. Rungs temp 0.7 (done, archived `.t07`, conv 8/15) → **0.5 (running)**
   → 0.3, fixed 32768 budget headroom, same 15 items; raw archived per-temp (`.t05`/`.t03`).
   Decision rule = **highest temp that converges WITHOUT a pass@1 regression** (AGENTS.md recipe).
2. **[THEN] grade the temp rungs** (post-sweep, from the `.tNN` archives) → pick the reliable
   temp → record in campaign-results.md. Then M2 idle (next item TBD).

## Reboot recovery

1. Restart the router (per-box recipe in AGENTS.md): `MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start …` → :8000.
2. For each `[RUNNING]` item, relaunch its driver (`lightsweep.sh` / `tempsweep.sh` with the
   same args) — it resumes from the on-disk results via done_ids / `--clean-stale`.
3. Re-arm any deferred wrappers (e.g. the qat-6bit "wait on PID" wrapper — repoint it at the
   new driver PID) and the box-idle / per-model monitors.
4. Sanity-check freshness with `benchmark/preflight.sh` before trusting a resumed run.

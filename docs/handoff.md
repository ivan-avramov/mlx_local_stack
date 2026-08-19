# Handoff — rewritten 2026-08-18 late evening (pre-compaction checkpoint, session continuing)

Single box (M5 Max 64 GB, driver AND worker). Stack pushed through `424276f`; fork pushed
through `07ed59e` (both remotes current as of ~21:00). Local-only stack commits after the
push: D11 queue row + this checkpoint. Intentional dirt unchanged: `main_models.yaml`
(three `Qwen3.8-27B` candidate entries <!-- allow-shorthand -->) + the live rung's jsonl.

## Live right now

- **Stage-2, `Qwen3.8-27B-mlx-uniform-4bit` humanevalplus arm**: regenerating its last ~9
  items (41/50 done, zero errors since the capped restart) under the rebuilt router
  (`MLX_VLM_CACHE_SESSION_MAX=2`, APC absent, suffix off — all verified at the worker).
  A background waiter fires on completion → next: **mbppplus 5-item pilot** (no wall-clock
  data on that bench), size → n=50, then swap to `Qwen3.8-27B-OptiQ-4.5bpw-mixed` for the
  same pair, then grade both (docker) with **M6a MTP speed probes in the grading window**.
- **All three distill downloads DONE** <!-- allow-shorthand --> in the HF cache: `TeichAI/Qwen3.8-27B-Fable-Distill`
  (M15), `barozp/Qwen3.8-27B-Opus-Distill-v2` (M16), `armand0e/Qwen3.6-35B-A3B-Fable-5-Distill`
  (M17). Conversions = quiet-window/overnight work (RAM-heavy; never beside a served model).
- Watcher + status files under `$STACK_WORKDIR/status/`; downloads log `distill_downloads.log`.

## Today's completed work (details in lab notebook / ledger / PLAN rows)

1. **Resume after OS upgrade** verified; handoff checkpoint committed.
2. **Workdir containment** hardened (AGENTS.md rule + memory + `grade.py` refuses nltk
   downloads without `NLTK_DATA`; stray `~/nltk_data` deleted by operator).
3. **qwen3_5 decode-rate attribution CORRECTED** (operator challenge): identical architecture
   across `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` and the `Qwen3.8-27B` family <!-- allow-shorthand -->;
   both ~24 tok/s suffix-OFF; only `Ornith-1.0-35B-mlx-uniform-4bit` (qwen3_5_moe, 76 tok/s)
   is fast. Stale suffix-ON-era impression; ledger/notebook corrected.
4. **MTP track created** (M6a/M6b/M13/M14): sidecars ship in BOTH qwen3_5 dense models
   (300 MB, int4); M13 closed-negative (base repo ships no head); M14 feasible
   (nvidia BF16 shard 14 has the 270-tensor block; DFlash alternative recorded).
5. **NVSY Switchyard plan** written (`docs/switchyard-plan.md`, O32 pointer, parked S1 row).
6. **Five Sonnet workers, all landed + architect-reviewed + committed**: D5 (workqueue
   SKIP-by-id, bench_watch `--tune` + SUSPECT-WRONG-FILE, `m1/status.py`), D7 (opencode in
   ROLES[coding], aider diagnostic tier, progress-gated session bound from the recovered
   design), M9 blocker (go/rust/java/javascript container grading, tamper detection), O30
   fork seed fix (fork `ab5273f`), D6 fork mitigations (fork `07ed59e`: shrink-on-retire +
   headroom eviction, BOTH OFF by default; worker caught the lazy-re-floor bug).
7. **H2 Haiku smoke PASSED 16/16** (all four languages incl. exercism-reference known-positives
   after the first pass left js/java stub-only; progress-gate 7/7) — M3/M4/M18 + Run C
   grading harness-validated.
8. **58 GB swap incident** root-caused (session floors × default cap 8, D6 audit) → router
   rebuilt capped, `runserver.sh` now sets cap=2 (operator-approved), 9 pressure-500 rows
   dropped + regenerating. D6 audit + D3 lineage reports in `$STACK_WORKDIR/scratch/`.

## Fork state & CI

Fork at `07ed59e` (= `0c1c8b1` + O30 seeds + D6 mitigations), tree CLEAN, pushed.
**Upstream-parity CI is RED and stays red — accepted**: upstream released v0.6.15 (21 new
files / 174 symbols / 84 registry entries vs the fork's sync point); not caused by our
commits. A partial restore was tried and REVERTED. **F1** (dedicated upstream-sync session)
is queued post-cycle, explicitly SEPARATE from and after D10.

## Scheduled / gated

- **D10**: submodule bump (`ab5273f`+`07ed59e`, features off by default) at the cycle
  boundary — after Stage-2 arms + M15/M16 funnels/screens + M3/M4/M18, before M11/M12.
  O30 seed fix is OUTPUT-DETERMINING for seeded runs; `--samples` valid only after.
- **D6 enablement**: gated on the 4-point live probe (footprint drop, resume tax, re-floor
  spike, eviction thrash) — code ships with D10, enabling is separate.
- **D11**: card + flip-to-public for the two `Qwen3.8-27B` passers <!-- allow-shorthand -->
  once Stage-2 n=50 numbers exist; `Qwen3.8-27B-static-mixed-4bit` stays private (Stage-1 FAIL).
- **Operator decisions pending**: NVSY S1 go (Sonnet-class arm, $10 cap recommended);
  fork push authority remains per-explicit-ask.

## Standing traps refreshed today

Watcher must be validated against a known row count (it silently reported QUEUED against a
healthy tuned run — now `--tune` + a loud diagnostic exist); memory-pressure 500s are infra
errors — drop + regenerate, never grade them into the denominator (O31); `rm` is aliased
interactive; full model names in ALL prose and commits (hooks catch docs/commits only).

**Order of resumption if context is lost: this file → `docs/PLAN.md` (queue) →
`docs/work-queue.json` (states) → `$STACK_WORKDIR/status/` (live runs).**

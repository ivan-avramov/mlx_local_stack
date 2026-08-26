# Handoff — 2026-08-26 night (M23 CLOSED BY CONSTRUCTION: the two 4-bit arms are the SAME MODEL; box IDLE)

Single box (M5 Max 64 GB). **NOTHING RUNNING except the bench router** (:8000, pid 89264, lean,
draft-OFF overlay, SESSION_MAX=2, APC absent, NO models resident — verified `pgrep -f
mlx_vlm.server` empty). Kill it by PID if the port is needed; it holds no state.

## THE HEADLINE

**M23 is answered, not re-run: conversion bias = exactly 0, because
`Qwen3.8-27B-mlx-uniform-4bit` and `mlx-community/Qwen3.8-27B-4bit` are the same model.**
Full-tensor md5 sweep: 2180/2180 tensors shared, **2179 identical**; sole delta =
`vision_tower.patch_embed.proj.weight` (our bf16 vision graft — text benches never touch it).
MLX uniform 4-bit gs64 quantization is deterministic; our conversion reproduced the official
quant byte-for-byte. Discovered when the post-C26-fix m23c pilots produced 10/10 byte-identical
outputs across "both" arms (incl. an 11,973-token generation). Full chain: lab-notebook
2026-08-26 evening. PLAN M23 row closed; ledger row re-headed IDENTITY; C33 opened (operator:
registry consolidation, drafter reframe, row pooling).

**Standing lesson (now in the lab notebook): before ANY conversion-vs-original A/B, hash the
tensors first.** A 2-minute md5 sweep bounds the effect at zero or licenses the arm; we spent
~20 h of arms against a mirror.

## Everything every m23/m23b "cross-arm difference" ever showed was SESSION NOISE

…between identical models: the 94.1-vs-87.5 humanevalplus gap, the "10× verbosity at a matched
seed" (seeds were dropped — C26), the DNF asymmetry. These are now C30's best replicate data:
five sessions of one model on overlapping items. Note also m23c official (seeds honored,
fork fix live): hep 100%/100% conv 100%, mbpp 80%/80% conv 100%, **zero runaways** — where
m23b (same model, unseeded) had 2 budget-hits. Whether honored seeds systematically avoid
runaway trajectories is an open C30 sub-question (n=1 session).

## Today's other completions (see git log 1f4aac6..HEAD; pushed through 38d2601)

- **C26 FIXED + PUSHED + BUMPED**: fork `ab5708a5` (sampler twins de-duplicated, guard widened,
  TDD 3617/0), stack submodule bumped (`38d2601`), fix verified live in `.venv`. 2-session
  byte-compare gate: EQUAL BYTES → paired design confirmed by operator (then mooted for M23 by
  the identity discovery — the gate result still stands for any future paired axis).
- **m23b + m23c official rows generated and graded** (tunes stay separate; m23c: hep 20/20
  100%/100%, mbpp 20/20 80%/80%, conv 100% both). m23c uniform: 5+5 pilot rows only, graded;
  full arm deliberately NOT launched (identity).
- **C28 orphan discipline held twice today** (killed driver → unload → `pgrep` verify).
- **C32 FIXED** (`e2946e3`): bare `--limit N` now broadcasts to all requested benches;
  unparseable specs refuse. (It had silently meant NO CAP — caught live at m23c pilot launch.)
- **Scoresheet kv provenance shipped** (`f7ef307`, `94f0701`, `ba828e7`): per-row
  TQ4/uniform4/fp16 + `·attnK/N` hybrid marker; gemma4 sliding-window KV stays unquantized even
  at kv_bits 4 (newly surfaced). C31: M24 low arm rejected; medium arm deferred to
  work-evaluation.

## NEXT SESSION

1. **Surface C33 to the operator** (registry consolidation: proposal = keep
   `caslca/Qwen3.8-27B-mlx-uniform-4bit` as canonical [restored vision tower + insurance-clone
   rule], retire the `Qwen3.8-27B-4bit` M23-reference entry; drafter upload activates only if a
   `Qwen3.8-27B` family recipe is ever picked; row-pooling question). <!-- allow-shorthand -->
2. **Push approval** for the post-`38d2601` commits (C32 fix, M23-closure docs, scoresheet
   regen if run).
3. Re-emit the scoresheet (m23c rows now graded) and update `docs/campaign-results.md`
   narrative where it cites m23-era cross-arm differences as model differences.
4. Then the PLAN queue: M24 provenance work, M9/M2 Stage-2 remainder — with ~20 h of A/B budget
   just refunded.

## Standing state

- Unpushed: everything after `38d2601` (C32 fix `e2946e3`+`5173b9d`, C32 row `1c12be1`,
  M23-closure docs commit). Fork fully pushed (`ab5708a5`).
- Working tree: only the intentional `main_models.yaml` local overrides (NEVER commit) + older
  untracked result dirs.
- The 2026-08-25 M23 INVALIDATION stands for its original reason (C28 cascade) AND is now
  doubly moot (identity). Never cite m23 DNF rates; m23-era rows live on only as C30 replicates.
- Bench-router hazard unchanged: draft-stripped overlay + SESSION_MAX=2 + APC absent, verified
  at the worker per arm.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md` (C33 is the top
operator item; C30, C31 open).**

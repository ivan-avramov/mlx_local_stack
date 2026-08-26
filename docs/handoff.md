# Handoff — 2026-08-26 evening (m23b DONE+graded; C26 FIXED, gate = EQUAL BYTES → paired m23c; box IDLE)

Single box (M5 Max 64 GB). **NOTHING RUNNING: no router, no worker, port 8000 clear** (verified
by PID kill + `pgrep -f mlx_vlm.server` empty + 0 listeners). The m23b arm, its watcher and the
bench router from the morning session are all finished/retired.

## What happened today (all committed locally; NOTHING pushed since `1f4aac6`)

1. **m23b official arm COMPLETE + GRADED** (`2587beb`): `Qwen3.8-27B-4bit`, 20/bench, seed 0, <!-- allow-shorthand -->
   deployed profile, probe-timeout **5200 PINNED**, draft-OFF overlay, clean exit, zero orphans.
   n=20 (MDE ±28pp — diagnostics, never verdicts): humanevalplus acc 95.0% [85,100] /
   strict@81920 85.0% / conv 90% (degenerate_repetition:2, 0 DNFs); mbppplus acc 80.0% [60,95] /
   strict 75.0% / conv 90% (budget_hit:1, degenerate_repetition:1; 1 self-terminating degen, 12% wall).
2. **C30 mbppplus session replicate extracted** (same commit): m23 vs m23b, same items/declared
   seeds → 1/20 byte-identical, log-token rank corr **0.666** (vs 0.84 on humanevalplus), 11/20
   items ≥2× token divergence (`Mbpp/300` 25×, `Mbpp/232` 20×), `Mbpp/306` 33,304→82,330 tok
   converged→budget-hit with finish==stop BOTH times. Session noise on a 20-item mbppplus arm ≈
   ±1–2 items of acc_strict. (Caveat: m23 side ran at the old 3600 s bound; no shared item errored.)
3. **C26 FIXED in the fork** (`../mlx-vlm` commit `ab5708a5`, TDD, suite 3617/0):
   `_PositionedTargetSampler` widened to the top_p/min_p/top_k filter chain and the two twins
   DE-DUPLICATED (server/generation.py imports the ar.py class). Guard now excludes only
   top_n_sigma/p_less/typical_p. Live verification at the deployed profile: same seed →
   byte-identical, different seeds → different (the original repro inverted).
   ⚠️ **Fork-local**: the stack submodule still points at `61845457` — any router started from
   the submodule runs the UNFIXED sampler. Push fork + bump submodule = FIRST action after the
   operator approves pushing.
4. **DESIGN GATE RUN — EQUAL BYTES** (2 full router/worker restarts, PYTHONPATH-fork router,
   draft-OFF overlay, deployed profile): seed 11 → 268=268 tok byte-identical; seed 12 →
   570=570 byte-identical. Per the pre-registered rule: **the M23 redesign is the PAIRED m23c
   re-run, both arms pinned 5200 s.** Caveat: probe = 2 seeds × 1 short prompt; 30k-token
   generations have more room for kernel float nondeterminism. The 2026-08-23 "cross-restart
   determinism NOT guaranteed" note predates the fix and is explained by it.
5. **Scoresheet kv provenance** (`f7ef307`, `94f0701`, `ba828e7`): per-row kv cell
   (TQ4/uniform4/fp16/n·a from the run MANIFEST) + `·attnK/N` hybrid marker (config-derived:
   qwen3_5-family 16/64, nemotron_h 6/52, gemma4 10/60 — gemma4 sliding-window RotatingKVCache
   stays UNQUANTIZED even at kv_bits 4, newly surfaced). n/a rows are NOT reconstructible from
   registry history (operator agreed — no archaeology).
6. **C31** (`70cd6b0`, strengthened in `94f0701`): M24 low arm REJECTED outright; medium arm
   DEFERRED — re-evaluated only at work-evaluation points, never queued in between. Only the
   effort→fingerprint provenance work stays live.

## NEXT SESSION, in order

1. **Ask the operator for push approval** (never push without in-turn approval). On approval:
   push the stack (through `2587beb`+docs), push the fork (`ab5708a5`), then
   `chore(stack): bump src/mlx-vlm -> ab5708a5` + `git submodule update --force` + verify.
2. **m23c paired re-run** (OPERATOR DECISION (2) is now answerable — surface the gate result
   first): both arms — `Qwen3.8-27B-4bit` AND the held `Qwen3.8-27B-mlx-uniform-4bit` — fresh <!-- allow-shorthand -->
   sessions on the FIXED serving path, tune `m23c`, seed 0, `--probe-timeout 5200` pinned on
   BOTH, draft-OFF overlay router (regenerate after any registry edit), 5-item seeded-random
   pilot per arm first, one resident model, unload + `pgrep` verify between arms.
   **Do NOT start m23c before the submodule bump lands** — a benchmark run must not depend on a
   PYTHONPATH override.
3. Then M24's provenance work / M9 / the rest of `docs/PLAN.md`.

## Standing state

- **Unpushed stack commits** (all after `1f4aac6`): `5e6c96c`, `f4dbb8e`, `b71eadf`, `a80e448`,
  `f7ef307`, `70cd6b0`, `94f0701`, `ba828e7`, `2587beb`, + today's final docs commit.
  Unpushed fork commit: `ab5708a5`.
- Working tree: only the intentional `main_models.yaml` local overrides (NEVER commit) and
  older untracked result dirs from previous sessions.
- The 2026-08-25 M23 result stays INVALIDATED (C28 cascade) — never cite its DNF rates. The
  m23 rows remain on disk as evidence under their own tune label; m23b/m23c never pool with them.
- C30 stays OPEN: with seeds now honored, the session-replicate question changes shape —
  paired designs absorb chaotic redraws; the variance bound deliverable still stands for
  historical single-session rows.
- Bench-router hazard unchanged: start from the draft-stripped overlay
  (`$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`), `MLX_VLM_CACHE_SESSION_MAX=2`, APC
  absent — verify all three at the worker cmdline/env per arm.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md` (C26 row has the
full fix + gate record; C30, C31 are the open items).**

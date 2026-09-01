# Handoff — 2026-08-31 late night checkpoint (M27 flipped; M30 ladder closed; M29 K merged + bumped, 1.18×; NA active; RCA of the swap incidents; NEXT = M29 H1 from a fresh session)

Single box (M5 Max 64 GB). **No run is live.** Router :8000 = draft-OFF bench overlay
(`$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`, SESSION_MAX=2, APC absent — verified `ps -Eww`;
listener pid in `$STACK_WORKDIR/m29/router_off.pid`, uv parent 68029), **no worker resident**.
Fork `../mlx-vlm` main = `dd2a2dcb` (pushed; branch `nemotron-h-with-states` pushed too);
`src/mlx-vlm` bumped to it (`14cfaa7`). Stack pushed through this checkpoint (see git log).

## Tonight's results (all in campaign-results / lab-notebook 2026-08-31)
- **M27 CERTIFIED + EXECUTED** (`3a200a9`): `Ornith-1.0-35B-mlx-uniform-4bit` ships `draft_kind: mtp`;
  drafter `caslca/Ornith-1.0-35B-mlx-uniform-4bit-mtp-drafter` public (sha-verified); the
  `caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter` card → CERTIFIED M6d. B menu = three certified
  triples (2.06× / 1.56× / 1.60×). SIX local `main_models.yaml` overrides in the worktree (NEVER commit).
- **C39 per-sample persistence** (`a38c476`) + ladder `--temp`/`--out-tag` (`40e088e`).
- **M30** `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` 24K temperature OFAT: STOPPED at Phase A per
  pre-registration — budget hits 3/5→2/5→2/5→2/5 across t1.0→0.3, 8/9 budget-hit draws still
  correct, same prompt hits at every temp. Temperature is not the lever; tune stays t1.0. C40 evidence.
- **M29 (C44 GO)**: mamba2 with-states kernel + ops twin replaced the per-position verify replay
  (K, `dd2a2dcb`; CPU 36 passed, GPU equivalence 22 passed). Re-probe **0.76× → 1.18×**
  (OFF 138.0 / ON 163.2 tok/s, acceptance 0.85–0.91, k=1) — STOP at 1.3×. Remainder ≈ 3.5 ms/round
  of drafter forward + syncs/Python → **H1 profile is next** (spec: `docs/specs/m29-h1-mtp-profile.md`).
  Registry stays draft-OFF for this model.
- **M5 Neural Accelerators ARE ACTIVE by default** (forced non-NA control `MLX_METAL_GPU_ARCH=applegpu_g16s`:
  fp16 55.9→14.9, 4-bit qmm 52.7→14.9 TFLOP/s). June "dead end" was an instrument error; AGENTS.md
  corrected (`1fafd43`). Prefill split @32K on the B 1st choice: MLP 43.5 % (already at the NA qmm
  rate), attention 26.5 %, GDN 21.9 % → no cheap prefill lever left on the hybrids.
- **RCA of two swap incidents (mine)**: bare-process MLX runs → allocator-cache bloat (default cache
  limit 65 GB on a 64 GB box; pool grew ∝ n² to 24 GB by 16K); `get_peak_memory` and `ps` RSS both
  blind. Rule in box-notes: bare-process MLX runs set `mx.set_cache_limit(≤4 GB)` +
  `mx.set_memory_limit`; footprint = `active + cache`. Server path is immune. Docker was a bystander.

## Operator decisions owed
- **C40** (strict single-number `reasoning_effective_ctx`; rec (a), reinforced by M30). **C41** (qwen3_5
  splitter TDD fix; rec: fix). **C42** (M14 block-size retry; rec NO). C31 deferred. Next O/C: **C45**.

## THE BOX QUEUE
1. **M29 H1 — run from a FRESH SESSION** (operator 2026-08-31): implement the env-gated MTP round
   profiler per `docs/specs/m29-h1-mtp-profile.md` on fork branch `nemotron-h-mtp-profile` (Sonnet
   implements, the verifier agent verifies, CPU-pinned tests), run it through `m1.mtp_probe --arm on` (server path;
   stop router 68032 by pid first, restart on the overlay after), apply the pre-registered decision
   rule (H2 → re-probe → k=2/3 only if head < 2 ms → OFAT if ≥ 1.3× → else close M29 → M12).
2. **M12 coding-at-depth d128k cliff check** (pre-registered, PLAN M12). Then M21 / M17 / D11.
3. Housekeeping: regenerate the bench overlay from the working registry before the next bench run
   (header predates the M27 flip); the fork sha in new manifests is now `dd2a2dcb`.

## Standing rules that bit tonight
Monitors: `/usr/bin/tail -F` + `/usr/bin/grep --line-buffered`, pid-file liveness with a known-positive
self-test (the first ladder watcher pattern-matched a cmdline and declared a live run dead). `cp`/`rm`
are interactive-aliased — `/bin/cp -f`, `rm -f`, verify. `mtp_probe` refuses to run while the campaign
router listens on :8000 — stop it by pid first (fail-loud, correct). Bare-process model loads: cache
cap + memory limit + `active+cache` watchdog, or don't. Full registry model names in commit messages too.

## Artifacts
M27 `$STACK_WORKDIR/m27/` (+ `flip/` cards & registry versions); M30 `$STACK_WORKDIR/nemo_ladder/`
(`phaseA.json`, per-temp logs) + `benchmark/results/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit/reasoning.a24k.t*.json`
(committed); M29 `$STACK_WORKDIR/m29/probe_k1/`; chains `$STACK_WORKDIR/quiet_window/`; NA + memory
probes `$STACK_WORKDIR/nax_probe/` (`memdebug_A/B.log`, `prefill_split_v3.log`); sidecars
`$STACK_WORKDIR/scratch/m6a/`. HF cache 253G + deliberate MTP-source fetches — don't "fix" it.

**Order of resumption: this file → `docs/specs/m29-h1-mtp-profile.md` → `docs/PLAN.md` → `docs/open-questions.md`.**

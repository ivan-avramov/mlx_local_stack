# Handoff — 2026-08-31 late-night checkpoint #2 (M29 H1 DONE, M29 CLOSED at 1.18×; NEXT = M12)

Single box (M5 Max 64 GB). **No run is live.** Router :8000 = draft-OFF bench overlay
(`$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`, SESSION_MAX=2, APC absent), listener pid in
`$STACK_WORKDIR/m29/router_off.pid` (77916, uv parent 77914), **no worker resident**.
Fork `../mlx-vlm`: main = `f5fff9b5` (profiler merged, pushed; branch `nemotron-h-mtp-profile` pushed too);
`src/mlx-vlm` bumped to it (`5f2f7d8`). Stack pushed through this checkpoint. Working tree: the SIX
intentional `main_models.yaml` local-path overrides (NEVER commit).

## This session (all in campaign-results / lab-notebook "2026-08-31 late night")
- **M29 H1 DONE**: env-gated MTP round profiler (`mlx_vlm/speculative/mtp_profile.py`;
  `MLX_VLM_MTP_PROFILE=1`, `MLX_VLM_MTP_PROFILE_HEAD=1`; eval-then-synchronize fences; zero calls when
  unset; 58 + 160 tests; mutation-checked known-positives). One server-path run
  (`$STACK_WORKDIR/m29/profile_k1/`: `worker_on.log`, `mtp_probe_result.json`, `chain3.log`, `mem.log`).
- **Result**: round 12.16 ms = verify 9.91 (81 %) + head 1.27 (`accept` 1.06 + `draft` 0.21) +
  syncs/Python 0.98 (`walk` 0.84, `rollback` 0.07, `yield` 0.04, `other` 0.03); 1.87 tok/round. The 2nd
  verified token costs 37 % of a full step. H2 trigger 11 % (< 50 %) → not met. Ceilings: 1.37× with the
  whole remainder removed, ≤ 1.23× realistic H2, ≤ 1.29× k=2/3 (optimistic). **M29 CLOSED at 1.18× per
  the pre-registered rule; `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` stays draft-OFF.** C42 rec NO
  reinforced; C44 closed. Prime suspect for the verify cost: the T>1 mamba2 with-states path (not
  MoE fan-out alone — `Ornith-1.0-35B-mlx-uniform-4bit` is a 3B-active MoE too and reaches 1.56×).
- Spec corrections recorded in `docs/specs/m29-h1-mtp-profile.md` (worker log lives in
  `$TMPDIR/mlx-manager-logs/<model>.log`; head-split is empty at k=1 for seed-path drafters; probe
  strips `draft_block_size`).

## Operator decisions (RULED 2026-08-31 late night)
- **C40 → (a)** largest-passing-rung on the strict curve + runaway-tax numbers (apply when M11 is next
  reported). **C41 → fix on the fork** (TDD; queued below). **C42 → NO.** C31 deferred. Nothing owed.
  Next O/C: **C45**.

## THE BOX QUEUE
1. **M12 coding-at-depth d128k cliff check** (pre-registered, PLAN M12): pilot-first, 5 seeded random
   items at d64k size the run; regenerate the bench overlay from the working registry FIRST (header
   predates the M27 flip). Then M21 / M17 / D11.
2. **C41 fork fix** (engineering, no box): `Qwen3_5MTPSplitter` separate-expert `postprocess`, detection
   fallback to root `model_type`, fail-loud on per-expert sidecar keys — TDD, implementer + verifier, then
   bump. Propose the plan before writing files.
3. Housekeeping: new manifests carry fork sha `f5fff9b5`.

## Standing rules that bit this session
- **`cut` in a monitor pipeline buffers** (no line-buffer flag): the worker-line watch stayed silent
  through 8,600 profiled rounds while its sibling chain-log branch worked. Use `awk '{...; fflush()}'`
  or nothing; every monitor gets a known-positive self-test line before it is trusted.
- Worker stderr goes to `$TMPDIR/mlx-manager-logs/<model>.log`, truncated on every load — copy it
  out inside the chain, before any restart.
- `m1.mtp_probe` refuses while :8000 is taken and strips `draft_block_size` from its temp registry.
- Bare-process model loads remain retired while the operator is at the machine (server path only;
  else cache cap + memory limit + `active+cache` watchdog). Full registry model names everywhere.

## Artifacts
M29 H1 `$STACK_WORKDIR/m29/profile_k1/` (+ `brief_h1.md`, the implementer brief); M29 K probe
`$STACK_WORKDIR/m29/probe_k1/`; M27 `$STACK_WORKDIR/m27/`; M30 `$STACK_WORKDIR/nemo_ladder/`; chains
`$STACK_WORKDIR/quiet_window/`; NA + memory probes `$STACK_WORKDIR/nax_probe/`; sidecars
`$STACK_WORKDIR/scratch/m6a/`. HF cache 253G + deliberate MTP-source fetches — don't "fix" it.

**Order of resumption: this file → `docs/PLAN.md` (M12) → `docs/open-questions.md` (C41).**

# Handoff — rewritten 2026-08-25 (M6b PASSED + registry-certified; O39 no-replication; M23 IN FLIGHT)

Single box (M5 Max 64 GB). **WORK RUNNING: M23 conversion-bias A/B.** Bench router on
:8000 (lean, **draft-OFF overlay** `$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml` —
REQUIRED for every bench start now, see below), `MLX_VLM_CACHE_SESSION_MAX=2`, APC off.
Verify live pids with `lsof -nP -iTCP:8000 -sTCP:LISTEN` + `pgrep -f run.py`.

## New since 2026-08-24 evening (all committed; pushed through `a55d382`, LOCAL AFTER THAT)

1. **M6b PASSED — the pick ships its (model, tune, predictor) triple.**
   `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` + t0.3 + `draft_kind: mtp` (native sidecar
   drafter). Paired 63-item OFAT: acc 0.9524 vs 0.9365 (delta +1.6pp CI [0.0,+4.8],
   TOST ±5pp EQUIVALENT, p_d=0.016, powered), 100% engagement @ 0.923 acceptance,
   ~2× decode, 0 degeneracy. Registry commit `ca4ed0f` (drafter = `caslca/` placeholder,
   NOT-YET-UPLOADED; local override in the working tree). Lab-notebook entry has the
   full table.
   **⚠️ STANDING CHANGE: bench router starts MUST strip draft fields** (the registry now
   serves mtp for the pick; measurement stays predictor-OFF). Overlay generator output:
   `$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`; regenerate after any registry edit.
2. **O39: the M3 inversion does NOT replicate on go** — 11/22 vs 12/22, McNemar p=1.0.
   M9 NOT triggered (C21 rule); C27 records it. Mechanism: path-infidelity give-ups are
   model-general (`Ornith-1.0-35B-mlx-uniform-4bit` shows them in go); TMPDIR prefix
   shape is output-determining for that mode (raw `$TMPDIR` vs `scratch/octmp`: 0/5 →
   2/5 same items). opencode pinned 1.18.15 via downloaded binary (brew drifted to
   1.18.20; version guard caught it).
3. **O40 COMPLETE at fork `61845457`**: batched PASS, cached PASS (C24 counters live),
   fail-loud verified at the worker contract (rc=3; note worker stderr lands in
   `$TMPDIR/mlx-manager-logs/<model>.log`, reopened per start). C25 fixed (penalties +
   inline mtp now fall back to plain decode). Bench rows persist `draft` counters
   (`479fd37`) — the engagement tripwire instrument.
4. **C26 seed bug CONFIRMED**: per-request seeds IGNORED on the cached path (byte-identical
   at t=1.0 across seeds). Single-sample runs unaffected; audit any multi-sample
   cached-path run before trusting pass^k/reliability numbers. Fork fix QUEUED (not started).

## M23 (IN FLIGHT): conversion-bias A/B, `Qwen3.8-27B-4bit` (official) vs `Qwen3.8-27B-mlx-uniform-4bit` <!-- allow-shorthand -->

Gate-3 2×50 recipe (humanevalplus 50 + mbppplus 50, seed 0 — REPLICATES the O37-era
draws), both arms fresh, t0.6 via registry `generation_defaults` (deployed profile, no
overrides), tune label `m23`, `--order model`, one resident model with unload between
arms, 5-item pilot per arm first (nested seeded draw → resume-clean). Official arm
pilot first (model already in hf cache). Rows: `benchmark/results/<model>/<bench>.m23.*`.

## Operator actions pending

- **Upload the drafter** `caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter`
  (source: `$STACK_WORKDIR/scratch/m6a/...-mtp-drafter`) to clear the NOT-YET-UPLOADED
  registry note.
- **Push**: local commits after pushed `a55d382`: `479fd37` (bench draft counters),
  `e7831d1` (O39/O40/C26 docs), `ca4ed0f` (M6b registry certification), plus M6b/M23
  docs commits as they land. Needs fresh in-turn approval.
- C26 fork fix funding (cached-path seed plumbing) — queue position vs M24.

## Standing footguns (delta from 2026-08-24)

- The mtp certification makes a **stale bench router the new top hazard**: a router
  started from the raw registry serves the pick mtp-ON and poisons any measurement that
  touches it. Always start bench routers from the draft-stripped overlay and verify
  drafter-flag state at the worker cmdline per arm.
- The evalplus per-item results file pads to the FULL corpus (164/378); restrict paired
  analyses to the generated ids or the CI tightens artificially.
- opencode brew updates silently; the probe's pin guard is the only defense — keep the
  1.18.15 binary in `$STACK_WORKDIR/o39/opencode-1.18.15/` for replications.
- A single-notification waiter must match FAILURE modes too, not only the success
  string — a grep-until armed on a condition that can never occur idles the pipeline
  silently (cost: ~9 h on 2026-08-24 night).
- rtk condenses git output — verify `rc` + `git log -1` after every commit; both guard
  hooks fired real rejections this session and the condensed output looked like success.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md` (C24–C27
closed/recorded; C26 fix and the drafter upload are the open items).**

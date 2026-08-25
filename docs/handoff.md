# Handoff — rewritten 2026-08-25 ~12:00 (M6b PASSED + registry-certified; O39 no-replication; M23 official arm IN FLIGHT; restart-safe checkpoint)

Single box (M5 Max 64 GB). **WORK RUNNING, all PPID 1 (survives session restarts):**

| what | pid | notes |
|---|---|---|
| bench router :8000 | 34276 | lean, **draft-OFF overlay** `$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`, SESSION_MAX=2, APC off |
| M23 official arm | 38762 | `Qwen3.8-27B-4bit` gate-3 2×50 (tune `m23`, seed 0, deployed); log `$STACK_WORKDIR/m23/arm_official.log` | <!-- allow-shorthand -->
| M23 watcher | 38763 | 5-min ticks -> `$STACK_WORKDIR/m23/watch_official.log`; exits when 38762 dies (by-PID check) |

At 11:56: hep 25/50 done (mean 290 s), mbpp 5/50 (pilot rows) — on pace for the
pilot-sized 4–6 h (NOT the row's ~2 h; mbpp tail items `Mbpp/306` 1432 s / `Mbpp/620`
802 s dominate).

**RESUMING SESSION: (1) verify the table above (`ps -o pid,ppid,etime -p 38762,38763,34276`);
(2) re-arm the alert Monitor: `tail -f $STACK_WORKDIR/m23/watch_official.log`, grep
`SUSPECTED|WATCH-EXIT|Traceback`, plus a waiter on pid 38762; (3) when the arm completes:
`POST /v1/models/unload` for `Qwen3.8-27B-4bit`, then the SECOND ARM — <!-- allow-shorthand -->
5-item pilot then full, SAME flags with `--models Qwen3.8-27B-mlx-uniform-4bit`:
`run.py generate --benches humanevalplus,mbppplus --limit humanevalplus=5,mbppplus=5 --seed 0 --tune m23 --sampling-profile deployed --order model`
(then limits 50,50; resume is seeded-nested); watcher: `python3 $STACK_WORKDIR/o39/o39_watch.py <pid> benchmark/results/Qwen3.8-27B-mlx-uniform-4bit/humanevalplus.m23.jsonl 300`;
(4) grade BOTH arms (`run.py grade --models <m> --benches humanevalplus,mbppplus --tune m23`);
(5) score per the M23 row: DNF counts, `acc_strict@81920`, loop taxonomy, paired per-item;
lab-notebook entry; PLAN row update.**

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

## Operator actions — ALL THREE RESOLVED 2026-08-25 (afternoon session)

- **Drafter UPLOADED**: `caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter` is
  public (anonymous resolve 200, all four files). Registry note cleared in `fee1721`;
  the box keeps its local workdir `draft_model` override in the working tree.
- **Pushed** through `722e739` (operator-approved in turn); `fee1721` + docs commits
  after it are LOCAL and need fresh approval as usual.
- **C26 fork fix funded AHEAD of M24** (operator ruling): starts after the M23 arms
  complete — no fork test runs against the box mid-measurement.

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

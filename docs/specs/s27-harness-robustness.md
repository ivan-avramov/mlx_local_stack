# S27 — harness robustness bundle (spec v1.0, 2026-11-20, for design review round 1 of 3)

Brief: C370 (principles P12–P17), the S27-P11 defects D1–D3, C365 (abort-vs-grade race), C368 (1) forward fix. One identity
rotation (tg1 + tg2 probe and chain closures). Four-eyes STRICT (design review, blind test-writer, implementer `claude -p`, change
review, verify; panel Sol + GLM + Claude Sonnet). Code map: the S27 designer notes (proc_guard / chain_core / p426_reconcile /
arm_runner / p426_harvest / corpus_tg2 line references are checked again by the implementer).

## 1. Goal

A leg survives a normal macOS box: background daemons, a slow process launch, an agent's package-manager cache. A guard checks what
the harness owns and does; noise is measured and recorded, enforced only when it can change the measured outcome; a harness fault
reruns that one item, never the leg (AGENTS.md, C370).

## 2. Settled (operator; not reopened)

C370 P12–P17; C365; C368 (1); C366 (superseded for future runs by §4.3 when this bundle ships, records kept); C338 / C339 (A8 plan);
C361 / C360 (host fingerprint; unchanged); the frozen stage-3 panel; the B4b-2 spec v1.4 (consumers; this bundle changes producers).

## 3. Ownership (P12; fixes D2)

1. A process is OURS iff any holds: it is in `guard.tracked` (its ancestry closure); its session id equals `probe_session` (the probe
   is the session leader, `chain_core` spawns it with `start_new_session=True`; the client and its descendants inherit it); its cwd or
   argv is under a guard root (`work`, `TMPDIR`, `grading-private`, and the run's hermetic `HOME` / `XDG_*` roots, added); its readable
   environment carries the run's `HOME` / `XDG_*` values; a container named `mlxbench-<run_id>-…`.
2. At cleanup every OURS process still alive is killed and verified gone (as today); one that cannot be verified gone →
   `uncertain` (as today). A same-session untracked process is OURS (today's `_sweep_excluded` skip is removed).
3. A process that is NOT ours (a foreign session, no attribution) and younger than the guard is recorded in a new list
   `foreign_new` `{pid, create_time, argv, sid}` — RECORD ONLY: never killed, never an orphan, never a refusal.
4. `orphans_unattributed` keeps its key and now holds only OURS processes that escaped (e.g. a re-parented descendant found by path or
   environment) and were killed; it may be non-empty in a certain cleanup (killed + verified). `chain_incident.cleanup_problems`:
   `CLEANUP_KEYS` gains `foreign_new`; "certain and complete" = `uncertain is False`, `completed is True`, `survivors` and
   `containers_remaining` empty. Every refusal site (`require_certain_cleanup`, `check_restart_eligible`, `p426_dnf_eligible`,
   `record_incident`) uses this one validator.
5. Residual (recorded): an agent process that calls `setsid`, leaves every guard root and clears its environment is foreign by this rule.

## 4. Order-tolerant reconciliation (P13; fixes D1, and the positives)

1. `p426_reconcile` kill cases gain `kill_boundary_late_record`: no failed line, `|C| == n == expected + 1`, positional pairing passes,
   the worker's completed count at the kill (`worker_summary_before.requests_completed − ready.requests_completed`) ∈
   {`expected`, `expected + 1`}. Accepted; the row records `order: "client_recorded_after_kill"`. The existing `kill_boundary`
   (`|C| == n == expected`) records `order: "client_recorded_before_kill"`.
2. Evidence for the order: `terminate_client` persists `signal_offset` (the events-file size at the SIGTERM) and the gate records each
   step's events offset; the late-record case requires the (n)th `step_finish` offset ≥ `signal_offset`.
3. `m62/inject_verify` causal chain (stall / loop): "the kill interrupts an in-flight generation" becomes order-tolerant — with a request
   in flight the existing proof (trailing interrupted / cancellation consistent); with none in flight (`in_flight_at_kill == 0`, worker
   `in_flight == 0`) the stop, the verified client kill and a reconciled row suffice, recorded `order: "no_request_in_flight"`. This
   supersedes C366's transfer for runs on the new identity (C366 records keep their rule).
4. Every other check that compares two independent events' order is listed by the implementer (search: `at_kill`, `in_flight`,
   `before`/`after` samples) and either made order-tolerant or justified in the change ledger.

## 5. Per-item retry (P16)

1. A HARNESS FAULT is one of: a reconciliation failure on an owned-cleanup-certain item that is not an integrity fault (§5.3); an
   owned-cleanup `uncertain` for that item; a grader infrastructure / transport error on that item; a hook infrastructure error on
   that item. Never an outcome of the item (a failed test, a budget hit, a loop, a tamper).
2. A harness fault ends that item with hook disposition `harness_fault` (new; `chain_hooks.KINDS` / `AFTER_KINDS`): the slot attempt is
   persisted (no ledger entry), `.stop` written, the invocation accepted for its prefix, and the SAME item reruns once, immediately
   (plan order), same seed (`seed_of(item)` is rerun-independent), records keyed by rerun index (`ready.json` / `items/<slot>` per
   attempt). A second harness fault on that item → a recorded harness-fault DNF (strict fail) and the leg continues. Caps: 1 rerun
   per item; harness-fault DNFs per leg ≤ 3 (separate from `MAX_P426_DNF`); the 4th → the sequencer pauses the leg for the designer
   (P17), never invalidates it.
3. INTEGRITY faults still invalidate the leg (unchanged path): wrong model / registry / weights, a worker identity drift, the agent's
   host fingerprint changing (C360), a contaminated work tree outside the item, a receipt chain break.
4. Consumers (B8 `_supersede_reasons`-style rules, `p426_freeze.leg_items_problems`, the harvest's `_check_references` /
   `_check_barrier`) accept exactly: one accepted attempt per slot, earlier attempts each `harness_fault` with a recorded reason. Both
   arms use the same rule.

## 6. C365 — abort vs an in-flight grade

Before `guard.kill_role("grader")` in `_run_item`'s abort path, the runner marks the grade worker cancelled; a grade that fails
after that mark is recorded `grade_cancelled` (in `termination` / ctx), never raised; the original exception (`SystemExit(143)`)
propagates with its cleanup record. Red test with a slow-grader seam.

## 7. Harvest (D3) and the tg2 view (C368 (1))

1. `p426_harvest._inventory`: a symlink under a run's private dirs (`home`, `data`, `state`, `cache`, `tmp`) is an excluded entry
   (`"symlink"`, `link` recorded, never followed), like a final-tree link; not `private_state` (its hashing refuses links).
2. `corpus_tg2.view_manifest`: for javascript a root `package-lock.json` absent from the prepared tree is omitted (as Rust's
   `Cargo.lock`). Red test on the recorded pilot shape.

## 8. Measure and pause (P14, P15, P17)

1. Watcher ticks add: memory pressure (`memory_pressure` / `vm.swapusage`: swap used and its growth), the top 5 CPU processes (name,
   %), the launch-latency probe (S27-P5). Thresholds (pre-set, revisable by the designer): swap growth > 2 GB in a tick, free memory
   level "critical", a non-harness process > 150 % CPU for 2 ticks, fresh-exec median > 1 s → an `ALERT` line (record only).
2. Item-boundary hold: a `HOLD` file in the leg's out root; the chain, at an accepted `done`, writes `.stop` with disposition `hold`
   (cleanup-only exit, invocation accepted for its prefix) and waits; on removal it resumes the remaining items as the next invocation
   (same load, plan order). The leg's deadline clock is suspended while held; the episode (start, end, reason) is recorded.
3. Tiers (P14), implemented as a table in `p426_wave2.classify_leg` / the watcher: INVALIDATE = §5.3; SPEED-INVALID (quality kept) =
   power off AC, watcher gaps, an ALERT during the leg, a hold; RECORD = `foreign_new`, background CPU below the threshold.

## 9. Identity and consequences

tg1 and tg2 probe identities and chain closures rotate (proc_guard, arm_runner, token_turn_gate, chain_*, p426_reconcile, p426_hooks,
corpus_tg2, m62/inject_verify). Consequences: stage 4 cannot reuse Wave 2 X legs (operator acknowledgement pending); C366's transfer is
refused on the new identity (`CANCEL_PATH` changes) and §4.3 replaces it; the tg2 chain restarts from the gate: new arms, positives,
rehearsal, v8, pilot, decider; stage-4 reuse loss accepted (C371). S27-P2 option B (C371) is built here: §12.

## 10. Acceptance (pre-registered)

1. Red tests first (blind test-writer) for §3–§8, including: a planted foreign-session process during an item → `foreign_new`, leg
   continues; a planted owned survivor (a client child that outlives it) → killed, recorded, certain; the recorded `java/sgf-parsing`
   numbers → `kill_boundary_late_record` accepted; a genuine count mismatch → still a fault; a stall with nothing in flight → PASS
   with its order; the C365 slow-grader case → exit 143 with the cleanup record; per-item retry end-to-end (fault once → rerun → accept;
   fault twice → DNF, leg continues; 4 DNFs → paused); an integrity fault → leg INVALID as before; the npx-cache symlinks → harvested,
   excluded; the lock-file view; the HOLD round trip.
2. Real-path checks on this box (no GPU): a detached daemon started in another session during a fake item is `foreign_new`; the
   failed leg `tg2-m76-n16-s1.a1`'s run homes harvest with the links excluded (dry run).
3. The full stack gate PASS on the merged commit; then the tg2 chain from the gate (C367's Go stands for the decider).

## 12. Push binding (C371, S27-P2 option B)

`local_gate.push_level` (stack, full level): after `check`'s fetch, the PASS receipt must carry `pushed_base`, and
`git diff --no-renames --name-only <pushed_base> <remote>/main -- <the four protected paths>` must be empty (the tg1 carrier JSON,
`noretry.js`, `toolbounds.js`, `datefreeze.js`); else refuse with a regate hint. Forks and tags unchanged. Red tests: a moved remote
`main` with the protected files unchanged → accepted; a moved remote `main` that edits `datefreeze.js` → refused; no `pushed_base` →
refused.

## 11. Out of scope

The B4b-2 consumers (their spec, v1.4); the tg2 corpus, draws, prompts, graders; the A8 statistics.

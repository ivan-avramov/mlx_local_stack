# S27 — harness robustness bundle (spec v1.1, 2026-11-20; design review r1 applied, ledger R1–R16; C372)

Brief: C370 (P12–P17), C372 (the retry split, the escaped-process residual), the S27-P11 defects D1–D3, C365, C368 (1), C371 (2) push
binding. One identity rotation (tg1 + tg2 probe and chain closures). Four-eyes STRICT (design review, blind test-writer, implementer
`claude -p`, change review, verify; panel Sol + GLM + Claude Sonnet). Ledger: `docs/reviews/s27-robustness/design-ledger-r1.md`.

## 1. Goal

A leg survives a normal macOS box (background daemons, slow process launches, package-manager caches) without weakening any check
that protects the measured outcome. A guard checks what the harness owns and does; noise is measured and recorded, enforced only
when it can change the measured outcome (AGENTS.md, C370).

## 2. Settled (operator; not reopened)

C370 P12–P17 as refined by C372; C365; C368 (1); C371 (2) option B; C366's records keep their rule (superseded for runs on the new
identity by §4.3); C338 / C339; C361 / C360; the frozen stage-3 panel; B4b-2 spec v1.4 (consumers).

## 3. Ownership (P12; D2)

1. **Session ownership** applies only when the probe is a session leader (`os.getsid(0) == os.getpid()` at guard construction, or the
   chain passes the session id explicitly and the manifest records it); otherwise ownership is tracked ancestry only (hand-run probes,
   preflights, tests).
2. **Order of tests** per live same-uid process younger than the guard: (a) in `guard.tracked` / its ancestry closure → OURS;
   (b) `getsid(pid) == probe_session` (when 3.1 applies) → OURS; (c) cwd / argv under a guard root (`work`, `TMPDIR`,
   `grading-private`, the run's `HOME` / `XDG_*`) or the readable environment carrying the run's `HOME` / `XDG_*` → OURS only with
   corroboration (a or b, or the environment match); a path-only match without corroboration → `foreign_new` with `path_match: true`;
   (d) anything else → `foreign_new`. A denied cwd / environ read on a process that (a) and (b) do not claim → `foreign_new` with
   `unreadable: true` (never `uncertain`); a denied read on a process (a) or (b) claims → `uncertain` (as today). A container named
   `mlxbench-<run_id>-…` is OURS.
3. **Cleanup:** every OURS process still alive is killed and verified gone (one kill-and-verify loop for tracked and untracked OURS
   alike); one not verified gone → `uncertain`. The `_sweep_excluded` same-session skip is removed (3.1 guards it).
4. **`foreign_new`** `{pid, create_time, argv (scrubbed), sid, path_match, unreadable}`: RECORD ONLY (never killed, never an orphan,
   never a refusal); capped at 64 entries plus a count.
5. **Receipt schema v2:** `cleanup_status.schema = 2` gains `foreign_new`; `orphans_unattributed` now holds OURS escapees that were
   killed and verified (may be non-empty in a certain cleanup) and leaves `CLEANUP_LISTS`; "certain and complete" = `uncertain is
   False`, `completed is True`, `survivors`, `containers_remaining` and `unknown` empty. `chain_incident.cleanup_problems` reads schema
   1 by the old rule (old identities, harvest and freeze reads of existing records) and schema 2 by this one; every refusal site
   (`require_certain_cleanup`, `check_restart_eligible`, `p426_dnf_eligible`, `record_incident`) uses that one validator.
6. **Persistence:** each item's `cleanup_status` (with `foreign_new` and the killed OURS escapees) is in its row (`row.cleanup_status`,
   schema + identity updated); the done hook, the leg classifier and the harvest read it from there.
7. **Residual (accepted, C372):** an agent child that calls `setsid`, leaves every guard root and clears its environment is
   `foreign_new` and is not killed; the next item's clean-tree and protected-path checks catch its effects.

## 4. Order-tolerant reconciliation (P13; D1, the positives)

1. `terminate_client` records, at the moment it reads `requests_at_kill`, the events-file size (`events_size_at_count`); it keeps
   `signal_offset` (size at SIGTERM, `None` when no signal was delivered); the gate records each step's END offset; all three persist
   in `termination` / the row.
2. `p426_reconcile` kill cases gain **`kill_boundary_late_record`**: `|C| == n == expected + 1`, positional pairing passes, the n-th
   `step_finish` END offset > `events_size_at_count` (the step's line completed after the count was read), the worker deltas hold;
   with no failed line, or with exactly one trailing failed line (`STREAM_CLOSED`, last) and `|S| == |C| + 1` (the client had started
   the next request). The row records `order` (`step_after_count` and, from `signal_offset`, `before_signal` / `after_signal` /
   `no_signal`). The existing `kill_boundary` records `order: "step_before_count"`.
3. **Positives (`m62/inject_verify.causal`, stall / loop).** Unchanged checks stay (stop reason, client kill, `killed_verified`,
   `cancel_wait_s` bound, and for loop the model-role `sleep 600` descendant kill). The in-flight link is order-tolerant: with a request
   in flight, the existing proof; with none — `in_flight_at_kill == 0`, worker `requests_started` unchanged from before to after,
   `after.in_flight == 0`, `trailing` not an interrupted kind — the verdict is **`PASS_NO_INFLIGHT`** (distinct; consumers that require a
   cancellation proof can tell it apart). The tg2 positives rule (`p426_wave2`, v8) accepts `PASS` and `PASS_NO_INFLIGHT` for stall /
   loop; C366's transfer is not used on the new identity.
4. The implementer lists every other check comparing two independent events' order (search `at_kill`, `in_flight`, before / after
   samples) and makes each order-tolerant or justifies it in the change ledger.

## 5. Harness faults: rerun before the outcome, flag after it (P16 as refined by C372)

1. **PRE-OUTCOME harness fault** (the item has no outcome yet): a grader infrastructure / transport error, a hook infrastructure
   error, an owned-cleanup `uncertain` that a second, independent cleanup scan then proves certain (survivors, containers and
   unknown empty; worker `in_flight == 0`; worker identity unchanged). → disposition `harness_fault`: the SAME item reruns once,
   immediately (plan order), same seed, after the cache session is reset (as the cheat path) and the settle check (worker
   `in_flight == 0`, same identity) passes. A second pre-outcome fault on that item → a recorded harness-fault DNF (strict fail), the
   leg continues.
2. **POST-OUTCOME accounting fault** (the item has an outcome — `passed` / `converged` known from its row — and reconciliation still
   fails after §4): NO rerun. The item keeps its outcome; the row is flagged `accounting_fault` with the failed checks; its tokens,
   latency and runaway-tax figures are descriptive only (excluded from token / latency aggregates, counted and listed per arm). Each
   item runs in its own session, so no state carries to the next item.
3. **Uncertain cleanup that stays uncertain** after the second scan → no rerun, no continuation: the chain HOLDS the leg (§8.2) for the
   designer; never continues on a possibly live owned process.
4. **INTEGRITY faults** still invalidate the leg (unchanged): wrong model / registry / weights, worker identity drift, the agent host
   fingerprint changing (C360), a contaminated work tree outside the item, a receipt-chain break, an unexplained worker / receipt /
   session-backend inconsistency that is not the item's own accounting.
5. **Caps and reporting:** 1 rerun per item; harness-fault DNFs per leg ≤ 3, enforced synchronously in the chain at the item barrier
   (before `.continue`): the 4th persists the DNF and the hold episode atomically and HOLDS. Per-arm counts of harness faults, reruns,
   harness-fault DNFs and accounting faults are reported fields; a pre-registered sensitivity analysis scores every item with a
   harness fault or accounting fault (either arm) as missing in both arms.
6. **Machinery (P426 chain):** `chain_hooks.KINDS` / `AFTER_KINDS` gain `harness_fault` and `hold`; `chain_rows.SLOT_DISPOSITIONS` gains
   `harness_fault` with a `slot_table` branch that queues `(slot, rerun_index + 1)` (separate from `MAX_RERUNS` / `cheat`;
   fault-then-cheat and cheat-then-fault each consume their own cap); `pump_barrier` accepts both in P426 mode; `run_p426_leg` runs a
   rerun step with its `rerun_index` and accepts `"hook"` for these; item records (`ready.json`, `items/<slot>`) are keyed by rerun
   index; `check_p426_ledger` accepts the rerun immediately after its fault; faulted attempts never enter `p426_invalid`. Consumers
   (`p426_freeze.leg_items_problems`, the harvest's `_check_references` / `_check_barrier`, B8 / B8-A8) accept exactly one accepted
   attempt per slot with earlier attempts each `harness_fault` and a recorded reason; a `PAUSED` leg state (held, not finished) is
   added to `LEG_STATES`, `classify_leg` and the harvest's rule table (a paused leg is resumed or archived by the designer, never
   harvested as a result).

## 6. C365 — abort vs an in-flight grade

In `_run_item`'s abort path, only when a primary exception is already in flight: mark the grade worker cancelled (it clears `queued`
and stops dequeuing) before `guard.kill_role("grader")`; a grade that fails after the mark is recorded `grade_cancelled` (in
`termination` / ctx), never raised; a failure stored before the mark stays a fault. The abort path's join is bounded
(`GRACEFUL_CLIENT_S`-scale, stated in code). The original exception (`SystemExit(143)`) propagates with its cleanup record. Red test
with a slow-grader seam.

## 7. Harvest (D3) and the tg2 view (C368 (1))

1. `p426_harvest._inventory`: a symlink under a run's private dirs (`home`, `data`, `state`, `cache`, `tmp`) is an excluded entry
   (`"symlink"`, never followed) whose `link` target is recorded through the portable scrubber (or as basename + sha256 when the
   scrubbed target still carries a box path); not `private_state`.
2. `corpus_tg2.view_manifest`: for javascript every `package-lock.json` absent from the prepared tree is omitted (as Rust's
   `Cargo.lock`). Red tests on the recorded pilot shape and a nested lock.

## 8. Measure, alert, hold (P14, P15, P17)

1. **Watcher ticks** add: swap used and its growth, the memory-pressure level, the top 5 CPU processes with pid, sid, start time,
   scrubbed argv and an ownership class (OURS by the chain's router / worker / probe identities and §3 attribution; `foreign`; `unknown`
   when unclassifiable), and the launch-latency probe (S27-P5). **ALERT** (record only) when: swap growth > 2 GB in a tick, pressure
   "critical", a `foreign` process > 150 % CPU for 2 ticks, fresh-exec median > 1 s.
2. **Hold** = the existing PAUSE file, extended to item boundaries: the chain checks it at each accepted `done` (before `.continue`),
   writes `.stop` with disposition `hold` (cleanup-only exit, the invocation accepted for its prefix), records the episode (start, end,
   reason), and waits; the leg's deadline is suspended for the held interval in both the chain and `Sequencer.supervise` (which reads
   the open episode and subtracts it). On release the chain re-runs the leg-entry checks (worker identity, `:8000` owner, AC power, no
   other GPU job; cache-session state recorded at hold and resume) before resuming the remaining items as the next invocation.
3. **Tiers (P14)** in `classify_leg` and the watcher: INVALIDATE = §5.4; SPEED-INVALID (quality kept) = off AC, watcher gaps, an ALERT in
   the leg, a hold, an accounting fault (that item only); RECORD = `foreign_new`, background CPU below the threshold; PAUSED = §5.3 /
   §5.5 until the designer resumes or archives.

## 9. Identity and consequences

tg1 and tg2 probe identities and chain closures rotate (proc_guard, arm_runner, token_turn_gate, chain_*, p426_reconcile, p426_hooks,
corpus_tg2, m62/inject_verify). Stage 4 cannot reuse the Wave 2 X legs (C371 (3)). The tg2 chain restarts from the gate: new arms,
positives (§4.3), rehearsal, v8, pilot, decider (C367's Go stands).

## 10. Acceptance (pre-registered)

1. Red tests first (blind test-writer): a foreign-session process during an item → `foreign_new`, leg continues; a denied read on a
   foreign daemon → `foreign_new unreadable`; a path-only match without corroboration → not killed; a hand-run (non-leader) probe →
   ownership by ancestry only; an owned survivor → killed, verified, recorded, certain; schema-1 records still validate; the recorded
   `java/sgf-parsing` numbers → `kill_boundary_late_record`; the trailing-failed variant; a genuine count mismatch on an item with an
   outcome → `accounting_fault`, outcome kept, no rerun; a pre-outcome grader transport error → rerun once → accepted; twice → DNF,
   leg continues; 4 DNFs → held; an uncertain cleanup → second scan certain → rerun, else held; an integrity fault → leg INVALID;
   stall with nothing in flight → `PASS_NO_INFLIGHT`, loop without the descendant kill → not observed; the C365 slow-grader case;
   the npx-cache links harvested as excluded with scrubbed targets; nested lock omitted; the HOLD round trip incl. the outer deadline;
   the push binding (§12).
2. Real-path checks on this box (no GPU): a detached daemon in another session during a fake item → `foreign_new`; the failed leg
   `tg2-m76-n16-s1.a1`'s run homes harvest with links excluded (dry run); the sgf-parsing events file confirms which side of
   `events_size_at_count` its 26th step ended (designer check before the freeze).
3. Stack gate PASS on the merged commit; then the tg2 chain from the gate.

## 12. Push binding (C371, S27-P2 option B)

`local_gate.push_level` (stack, full level): after `check`'s fetch, the PASS receipt must carry `pushed_base`, and
`git diff --no-renames --name-only <pushed_base> <remote>/main -- <the four protected paths>` must be empty (the tg1 carrier JSON,
`noretry.js`, `toolbounds.js`, `datefreeze.js`); else refuse with a regate hint. Forks and tags unchanged. Red tests: a moved remote
`main` with the protected files unchanged → accepted; a moved remote `main` that edits `datefreeze.js` → refused; no `pushed_base` →
refused.

## 11. Out of scope

The B4b-2 consumers (their spec v1.4, which reads these rows: `accounting_fault`, `cleanup_status`, rerun attempts); the tg2 corpus,
draws, prompts, graders; the A8 statistics.

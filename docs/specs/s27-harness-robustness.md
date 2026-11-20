# S27 — harness robustness bundle (spec v1.4, 2026-11-20; FINAL design — review r1–r3 applied, ledgers R, V, W; C372; v1.4 = the §10.2 designer-check amendment to §4.2, S28-P4, not re-reviewed; PENDING the operator)

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
   (d) anything else → `foreign_new`. Any denied read (start order, liveness, cwd, environ) on a process that (a) and (b) do not
   claim → `foreign_new` with `unreadable: true` (never `uncertain`); a denied read on a process (a) or (b) claims, or an
   unreadable session id, → `uncertain` (as today). The ownership tests run before any read that can mark a process unreadable. A container named
   `mlxbench-<run_id>-…` is OURS.
3. **Cleanup:** every OURS process still alive is killed and verified gone (one kill-and-verify loop for tracked and untracked OURS
   alike); one not verified gone → `uncertain`. The `_sweep_excluded` same-session skip is removed (3.1 guards it).
4. **`foreign_new`** `{pid, create_time, argv (scrubbed), sid, path_match, unreadable}`: RECORD ONLY (never killed, never an orphan,
   never a refusal); capped at 64 entries plus a count. An unclaimed unreadable process is listed only when it is not provably older
   than the guard (age readable); the rest are counted (`unreadable_count`), not listed.
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

1. `terminate_client` records, under the same lock as `requests_at_kill`, the ingested byte position of the events stream
   (`ingested_offset_at_count`) and the file size (`events_size_at_count`, supplementary); it keeps
   `signal_offset` (size at SIGTERM, `None` when no signal was delivered); the gate records each step's END offset; all three persist
   in `termination` / the row.
2. `p426_reconcile` kill cases gain **`kill_boundary_late_record`**: `|C| == n == expected + 1`, positional pairing passes, the n-th
   `step_finish` END offset > `ingested_offset_at_count` (the step was ingested after the count was read, whether its bytes were
   written before or after), the worker deltas hold;
   with no failed line, or with exactly one trailing failed line (`STREAM_CLOSED`, last) and `|S| == |C| + 1` (the client had started
   the next request). The row records `order` (`step_after_count` and, from `signal_offset`, `before_signal` / `after_signal` /
   `no_signal`). The existing `kill_boundary` records `order: "step_before_count"`.
   **Second shape, `order: "unpublished"` (v1.4, from the §10.2 designer check — the recorded D1 case):** the n-th step_finish is
   absent from the stream; the n-th request_usage entry is the export's one trailing `unpublished` message (`reconciliation.trailing
   == "unpublished"`, `unmatched_export_messages == 1`), its message id equals the stream's last `step_start` (opened after the
   (n−1)-th step_finish, no step_finish of its own; `tool_use` lines and one trailing client `error` event allowed), `|S| == |C| == n`,
   positional pairing on all n entries passes (its generated / prompt tokens equal the worker's n-th completion), the worker deltas
   hold (`requests_completed` delta == `requests_started` delta == n, `in_flight_at_kill == 0`, `after.in_flight == 0`). The offsets
   are recorded but not required for this shape.
3. **Positives (`m62/inject_verify.causal`, stall / loop).** Unchanged checks stay (stop reason, client kill, `killed_verified`,
   `cancel_wait_s` bound, and for loop the model-role `sleep 600` descendant kill). The in-flight link is order-tolerant: with a request
   in flight, the existing proof; with none — `in_flight_at_kill == 0`, worker `requests_started` unchanged from before to after,
   `after.in_flight == 0`, `trailing` not an interrupted kind — the verdict is **`PASS_NO_INFLIGHT`** (distinct; consumers that require a
   cancellation proof can tell it apart). The tg2 positives rule (`p426_wave2`, v8) accepts `PASS` and `PASS_NO_INFLIGHT` for stall /
   loop; every consumer of the verdict strings gains `PASS_NO_INFLIGHT`: `p426_freeze.inject_accepted`, `cmd_v8_tg2`, the
   harvest, `m62/run_m62_live.py`'s results (red test: a record with `PASS_NO_INFLIGHT` freezes). C366's transfer is not used on the
   new identity.
5. **Interrupt positive (C373).** Each tg2 positives record (and tg1's positives, which share the cancel path) adds one deterministic
   run, `interrupt`: on the pilot item, the harness itself issues the stop once the worker reports a generation in flight (`/metrics`
   polled until `in_flight >= 1`, deadline 120 s, else the run is retried once, then FAIL), through the same `terminate_client` path.
   PASS requires the existing in-flight proof (trailing interrupted, cancellation consistent, client kill verified, `cancel_wait_s`
   bound). The record is PASS only if `interrupt` is PASS; stall / loop then prove detection (PASS or `PASS_NO_INFLIGHT`). v8 checks it;
   the ship recommendation states which proof each record used.
6. The implementer lists every other check comparing two independent events' order (search `at_kill`, `in_flight`, before / after
   samples) and makes each order-tolerant or justifies it in the change ledger.

## 5. Harness faults: rerun before the outcome, flag after it (P16 as refined by C372)

1. **Grade-only fault → regrade in the probe, never regenerate.** A grader INFRASTRUCTURE fault — a closed list: container spawn
   failure, docker daemon / transport loss, image unavailable, a grader-path connection loss — on the FINAL grade is retried inside
   `_run_item` (same guard; the final snapshot is taken once and kept for the whole item), up to 2 more times. Only the third fault
   writes the `grader_infra` stamp, with the generation evidence (gate report, receipts, export) persisted, and the item becomes a
   recorded `grade_fault` DNF (strict fail, its tokens kept); the leg continues. An INTERIM grade's infrastructure fault (the
   concurrent `GradeWorker` while the client still generates) is a pre-outcome fault (§5.2). A grader TIMEOUT, `mem_kill`, OOM or tamper result is the item's OUTCOME
   (unchanged), never a fault.
2. **PRE-OUTCOME harness fault** (before the generation finished): a hook infrastructure error at `ready`, an interim grader
   infrastructure fault (§5.1), or an owned-cleanup
   `uncertain` that a second, independent scan then proves certain (§5.8). → disposition `harness_fault`: the SAME item reruns once,
   immediately (plan order), same seed, after the cache session is reset (as the cheat path) and the settle check (worker
   `in_flight == 0`, same identity, `:8000` owner) passes. A second pre-outcome fault on that item → a recorded `harness_fault_dnf`
   (strict fail), the leg continues.
3. **POST-OUTCOME accounting fault** (the item has an outcome and a §5.9 accounting check still fails after §4): NO rerun. Disposition
   `accounting_fault` (new): the done hook writes a sealed sidecar `items/<slot>.accounting.json` (slot, row sha, item-record sha,
   the failed checks) and continues after the settle check (worker `in_flight == 0`, same identity, `:8000` owner; a failed settle →
   integrity, HOLD). `chain_rows` exposes the row with `accounting_fault: true`; its tokens, latency and runaway-tax figures are
   descriptive only (excluded from aggregates, listed per arm). A hook infrastructure error at `done` (the row exists) is handled the
   same way when the sidecar can be persisted; if it cannot, the leg is PAUSED.
4. **Uncertain cleanup that stays uncertain** after the second scan → no rerun, no continuation: the leg is PAUSED (§5.8) for the
   designer; never continues on a possibly live owned process.
5. **INTEGRITY faults** still invalidate the leg (unchanged): wrong model / registry / weights, worker identity drift, the agent host
   fingerprint changing (C360), a contaminated work tree outside the item, a receipt-chain break, an unexplained worker / receipt /
   session-backend inconsistency that is not the item's own accounting.
6. **Caps and reporting:** 1 rerun per item; `harness_fault_dnf` + `grade_fault` DNFs per leg ≤ 3, enforced synchronously in the chain at the item barrier
   (before `.continue`): the 4th persists the DNF and the hold episode atomically and HOLDS. Per-arm counts of harness faults, reruns,
   harness-fault DNFs and accounting faults are reported fields; a pre-registered sensitivity analysis scores every item with a
   harness fault or accounting fault (either arm) as missing in both arms.
7. **Machinery (P426 chain):** `chain_hooks.KINDS` / `AFTER_KINDS` gain `harness_fault`, `accounting_fault` and `hold`;
   `chain_rows.SLOT_DISPOSITIONS` gains `harness_fault` with a `slot_table` branch that queues `(slot, 1)`; P426 legs have no cheat
   rerun (their done path accepts or invalidates only), so a P426 slot's rerun index is 0 or 1 and `validate_progress` checks that
   bound for P426 (`MAX_RERUNS` / `exhausted` unchanged for per-arm legs); `harness_fault_dnf` and `grade_fault` are DNF records
   (stored in a second list `chain.p426_harness_dnf` with sealed sidecars `items/<slot>.harness_dnf.json`, a ledger kind `dnf`, scored
   strict 0, counted under the cap above, separate from `MAX_P426_DNF`'s transport DNFs in `p426_dnf`; `check_p426_ledger`'s DNF
   equality, `chain_rows._dnf_rows` and `leg_items_problems` read both lists); for per-arm legs the harness-fault rerun cap and the
   cheat rerun cap (`MAX_RERUNS`) are consumed independently; `pump_barrier` accepts both in P426 mode; `run_p426_leg` runs a
   rerun step with its `rerun_index` and accepts `"hook"` for these; item records (`ready.json`, `items/<slot>`) are keyed by rerun
   index; `check_p426_ledger` accepts the rerun immediately after its fault; faulted attempts never enter `p426_invalid`. Consumers
   (`p426_freeze.leg_items_problems`, the harvest's `_check_references` / `_check_barrier`, B8 / B8-A8) accept exactly one accepted
   attempt per slot with earlier attempts each `harness_fault` and a recorded reason, OR a `harness_fault_dnf` / `grade_fault` DNF as
   the slot's terminal record; a `PAUSED` leg state (held, not finished) is
   added to `LEG_STATES`, `classify_leg` and the harvest's rule table (a paused leg is resumed or archived by the designer, never
   harvested as a result).

8. **The abort route.** An uncertain cleanup or a grader / hook infrastructure fault that ends the probe writes a typed abort stamp
   (`cause: cleanup_uncertain | grader_infra | hook_infra`, with the cleanup receipt); `handle_p426_incomplete` routes these BEFORE its
   DNF-cause check. For `cleanup_uncertain` the CHAIN runs the second scan itself (by the recorded probe session id when it led its
   session, the run's hermetic roots, the container-name prefix; the same kill-and-verify rule for OURS; deadline 60 s; evidence
   persisted; anything not verified gone → PAUSED), then requires worker
   `in_flight == 0` and an unchanged identity → `harness_fault` rerun; otherwise the leg is PAUSED: `chain.json` records the episode,
   the chain launches nothing, and resumes only on the designer's release (no live probe is needed for a pause). Routing by stage:
   `ready` / `generation` (no outcome) → §5.2's one rerun; `final_grade` (the in-probe regrades exhausted) → the `grade_fault` DNF
   (§5.1); `done` (outcome present) → §5.3 (or PAUSED if the sidecar cannot be persisted).
9. **Accounting vs integrity (closed table).** After the §4 order-tolerant cases have been tried: `boundary_count`, `unaccounted_count`,
   `pairing` → accounting (§5.3). `serial`, `session_backend`, `started_terminated`, `failed_lines` beyond the allowed variants, and
   `worker_deltas` beyond the late-record explanation → integrity (§5.5). Any check not in this table → integrity.

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
3. **Tiers (P14)** in `classify_leg` and the watcher: INVALIDATE = §5.5; SPEED-INVALID (quality kept) = off AC, watcher gaps, an ALERT in
   the leg, a hold, an accounting fault (that item only); RECORD = `foreign_new`, background CPU below the threshold; PAUSED = §5.4 /
   §5.6 until the designer resumes or archives.

## 9. Identity and consequences

tg1 and tg2 probe identities and chain closures rotate (proc_guard, arm_runner, token_turn_gate, chain_*, p426_reconcile, p426_hooks,
corpus_tg2, m62/inject_verify). Stage 4 cannot reuse the Wave 2 X legs (C371 (3)). The tg2 chain restarts from the gate: new arms,
positives (§4.3), rehearsal, v8, pilot, decider (C367's Go stands).

## 10. Acceptance (pre-registered)

1. Red tests first (blind test-writer): a foreign-session process during an item → `foreign_new`, leg continues; a denied read on a
   foreign daemon → `foreign_new unreadable`; a path-only match without corroboration → not killed; a hand-run (non-leader) probe →
   ownership by ancestry only; an owned survivor → killed, verified, recorded, certain; schema-1 records still validate; the recorded
   `java/sgf-parsing` numbers → `kill_boundary_late_record`; the trailing-failed variant; a genuine count mismatch on an item with an
   outcome → `accounting_fault`, outcome kept, sidecar sealed, settle checked, no rerun; a worker-delta mismatch beyond the late-record
   case → integrity; a grader transport fault on a finished item → regrade (no regeneration) → accepted; three → `grade_fault` DNF;
   a grader timeout / mem_kill → the outcome, no regrade; the final-grade regrade runs in the probe with the snapshot kept (two
   faults then a pass → accepted, one generation); an interim grader infrastructure fault → one rerun; a `done` hook
   infrastructure fault → `accounting_fault` (or PAUSED when the sidecar cannot be written); the chain scan kills and verifies an
   OURS survivor, else PAUSED; the harness DNFs live in `p426_harness_dnf` and pass the ledger check beside a transport DNF; a hook infrastructure fault at ready → rerun once; twice →
   `harness_fault_dnf`, leg continues; the ingest-lag order (step bytes before the count, ingested after) → late record accepted; 4 DNFs → held; an uncertain cleanup → second scan certain → rerun, else held; an integrity fault → leg INVALID;
   stall with nothing in flight → `PASS_NO_INFLIGHT` (and it freezes in v8), loop without the descendant kill → not observed; a
   denied start-order read on a foreign daemon → `foreign_new unreadable`; the abort route (`cleanup_uncertain` → chain scan →
   rerun, or PAUSED with no live probe); the C365 slow-grader case;
   the npx-cache links harvested as excluded with scrubbed targets; nested lock omitted; the HOLD round trip incl. the outer deadline;
   the push binding (§12).
2. Real-path checks on this box (no GPU): a detached daemon in another session during a fake item → `foreign_new`; the failed leg
   `tg2-m76-n16-s1.a1`'s run homes harvest with links excluded (dry run); the sgf-parsing events file shows where its 26th step
   ended relative to the bytes ingested before the kill decision (designer check before the freeze).
   **Result (2026-11-20, S28-P4):** the 26th step never published a step_finish. Stream: step_start `msg_1f6b55ed0001…` at event
   time 445.13, its shell `tool_use` 445.65–450.70, the client's transport `error` at 451.04 (the last line, byte 104595–104857); 25
   step_finish lines. Worker: request 26 started 18:07:24.284, completed 18:07:28.071 (114 generated / 14579 prompt); before == after
   at the kill (549 / 549, in_flight 0). The stop landed at ≈ 450.96 (`inflight_s_at_stop` 5.83 s after the step_start), before the
   step_finish (prior steps: tool end → step_finish ≈ 1.1 s). `requests_at_kill` = 25 (stream count); the row's 26th entry came from
   the export as trailing `unpublished` (114 / 14579, pairs with the worker). → §4.2's second shape (`order: "unpublished"`); the
   red test uses these numbers.
3. Stack gate PASS on the merged commit; then the tg2 chain from the gate.

## 12. Push binding (C371, S27-P2 option B)

Hazard covered: the gate's closure test proved "the build does not edit the protected files" against the base the gate saw; if the
remote `main` moved and changed a protected file since, that proof no longer describes the push. `local_gate.push_level` (stack,
`full` level, non-evidence refs only; `docs-only` / `data-only` return earlier): after `check`'s fetch, one helper reads the PASS
receipt DOCUMENT; it must carry `pushed_base`, the commit must exist in the repo (else refuse), and
`git diff --no-renames --name-only <pushed_base> <remote>/main -- <PROTECTED_PUSH_PATHS>` must succeed and be empty; any git error
refuses; a refusal prints a regate hint. `PROTECTED_PUSH_PATHS` = the existing four-file set (`arm_opencode` / `arm_specs`'s
constant, imported; a test pins equality with the closure test's paths):
`benchmark/opencode_bench_v2_web_tg1.json`, `benchmark/opencode_plugins/noretry.js`, `benchmark/opencode_plugins/toolbounds.js`,
`benchmark/opencode_plugins/datefreeze.js`. Forks and tags unchanged. Red tests: a moved remote
`main` with the protected files unchanged → accepted; a moved remote `main` that edits `datefreeze.js` → refused; no `pushed_base` →
refused; a `pushed_base` absent from the repo → refused; a non-`main` pushed ref at level `full` → the same rule.

## 11. Out of scope

The B4b-2 consumers (their spec v1.4, which reads these rows: `accounting_fault`, `cleanup_status`, rerun attempts); the tg2 corpus,
draws, prompts, graders; the A8 statistics.

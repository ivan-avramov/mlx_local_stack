**Verification of my round-1 findings against spec v1.1.** I read the diff, the ledger, `local_gate.py` (`push_level`, `pushed_base`, `pass_receipt`) and re-checked the touched code. I did not read `p426_hooks.py`, `p426_harvest._inventory` or `classify_leg` in full this round. P12 and the cross-consumer parts of P1 rest on the spec text only.

| R1 finding | Status | Why |
|---|---|---|
| P1 rerun machinery | Resolved, with one gap (F6) | §5.6 names `KINDS`, `SLOT_DISPOSITIONS`, the `slot_table` branch, `pump_barrier`, `run_p426_leg`, the ledger, the cache reset and the settle check. |
| P2 outcome-conditioned retry | Resolved | C372 splits the cases. Post-outcome accounting faults keep the outcome with no second draw. Per-arm counts and a missing-in-both sensitivity analysis are pre-registered. The remaining bias risk is in F3. |
| P3 uncertain cleanup then rerun | Partly resolved | Second scan, settle and HOLD are specified. The abort route and who runs the scan are still unspecified (F4). |
| P4 late-record rule | Partly resolved | The end offset, trailing-failed variant, `no_signal` and the order field are in. The reference point is still wrong for the ingest-lag order (F1). |
| P5 session ownership | Resolved | §3.1 makes it leader-only or explicitly passed. §3.2(c) requires corroboration for path-only matches. §3.3 has one kill-and-verify loop. |
| P6 `no_request_in_flight` | Resolved for the verdict; consumer gap in F5 | `PASS_NO_INFLIGHT` is distinct, has strict conditions, and the loop descendant kill is kept. |
| P7 per-item persistence | Resolved | `row.cleanup_status` is written after `run_item`'s finally, so it is available when the row is built. |
| P8 denied read on a foreign daemon | Resolved for cwd/environ; residual in F7 | §3.2 sends an unclaimed process with a denied read to `foreign_new unreadable`. |
| P9 HOLD | Resolved | Leg-entry checks run on resume, PAUSE is reused, and the supervise deadline is subtracted. The abort-path hold gap is in F4. |
| P10 receipt schema | Resolved | Schema v2 with schema-1 compatibility, `unknown` kept in the certain rule, `foreign_new` capped. |
| P11 C365 | Resolved | Primary exception only, queue cleared, join bounded, earlier failures stay faults. |
| P12 symlink target, nested lock | Resolved | Scrubbed target and nested-lock omission are specified. |

### F1 — The late-record reference point misses the ingest-lag order
- **Severity:** major. **Evidence:** hypothesis. The code path is confirmed; which order occurred in the `sgf-parsing` run is not known.
- **Location:** spec §4.1–4.2; `arm_runner.py:503`, `599-612`; `token_turn_gate.py:283-296`.
- **Problem:** `requests_at_kill` counts ingested steps, but the ingester lags the file (`stop.wait(0.05)` poll). `events_size_at_count` is the file size, not the ingested position. A step whose line was written before the count but fed after it has END offset ≤ `events_size_at_count`. It still produces `n == expected + 1`, and the rule rejects it. That is a benign order, and the same "bytes written earlier but ingested later" case `token_turn_gate.py:440` already distinguishes.
- **Scenario:** The client writes step 26 a few milliseconds before the count is read. The ingester reaches it after. The row then has `n=26` and `expected=25`, and it takes `accounting_fault` — the D1 outcome under a new name.
- **Proposed change:**
  - Record `stream.offset`, the ingested byte position, under the same lock as `requests_at_kill`.
  - Define late-record as the n-th END offset > that ingested offset.
  - Keep the file size as supplementary evidence.
  - The §10.2 designer check should state which of the two positions the 26th step lies after.

### F2 — The accounting versus integrity boundary has no operational definition
- **Severity:** major. **Evidence:** confirmed (the checks in `_reconcile` are one flat list).
- **Location:** spec §5.2, §5.4; `p426_reconcile.py:275-348`.
- **Problem:** §5.2 sends reconciliation failures after an outcome to `accounting_fault`. §5.4 invalidates the leg for "an unexplained worker / receipt / session-backend inconsistency that is not the item's own accounting". Nothing says which `_reconcile` checks fall on which side: `serial`, `worker_deltas`, `started_terminated`, `session_backend`, `boundary_count`, `unaccounted_count`, `pairing`, `failed_lines`.
- **Scenario:**
  - A worker-delta mismatch from a second session using the worker is classified as `accounting_fault`, and the item is kept.
  - Or a harmless `boundary_count` mismatch is classified as integrity, and the leg is invalidated again.
  - The implementer and the blind test-writer will decide differently.
- **Proposed change:** Add a closed table.
  - `boundary_count`, `unaccounted_count` and `pairing` can be `accounting_fault`, only after the §4 order-tolerant cases have been tried.
  - `serial`, `session_backend` and `worker_deltas` beyond the late-record explanation are integrity.
  - Any check not in the table is integrity.

### F3 — Grader faults in the pre-outcome class can be candidate-caused
- **Severity:** major. **Evidence:** hypothesis.
- **Location:** spec §5.1; `corpus_tg2.py:96-110`; `arm_runner.py:742-751`.
- **Problem:** "Grader infrastructure / transport error" is not defined. A grader timeout, `mem_kill` or OOM can be produced by the agent's code, such as a test that hangs or an allocation bomb. The corpus already scores some of these as outcomes (`grader_mem_kill`, `grader_oom`). The grader's final grade also runs after the whole generation. A rerun redraws the generation for an item whose trajectory is already known (budget hit, loop), so P2's bias returns for any fault class that correlates with agent behaviour.
- **Scenario:** An agent's JS test spawns a runaway process, the grader times out, the item is "harness fault, rerun", and the second attempt is clean.
- **Proposed change:**
  - List the harness-fault grader classes explicitly: spawn failure, docker daemon or transport loss, router or worker connection loss in the grader path.
  - Anything with a timeout, mem_kill, OOM or tamper marker is an outcome and not rerun.
  - For a grade-only fault, consider re-grading the preserved snapshot instead of regenerating. The final tree and evidence are kept, and AGENTS.md prefers regrade over rerun.

### F4 — The uncertain-cleanup route still has no mechanism, and the hold is defined at a barrier that does not exist there
- **Severity:** major. **Evidence:** confirmed.
- **Location:** spec §5.1, §5.3, §5.5, §8.2; `arm_runner.py:845-860`, `1292-1328`; `chain_core.py:2627-2652`.
- **Problem:**
  - An uncertain cleanup raises `TransportAbort` from `guard.cleanup()` inside `_run_item`'s finally. There is no row and no `.done`.
  - The probe exits with an abort manifest, and the chain reaches `handle_p426_incomplete`. That path requires a DNF cause and a certain cleanup, so it is refused today. The spec does not say how this becomes `harness_fault`.
  - It also does not say who runs the "second, independent scan". The probe's guard is gone, so the scan would have to be chain-side. The chain has no tracked set and would need the probe session id and the run's hermetic roots.
  - §8.2 defines HOLD as `.stop` written at an accepted `done`. For §5.3 and the 4th-DNF case the probe is already dead, or the barrier is `done` of the item that just failed.
- **Scenario:** The probe aborts with `uncertain`. The chain has no route that satisfies "second scan certain, then rerun". It raises the systemic abort that C372 wanted to avoid, or it implements ad hoc code at review.
- **Proposed change:** Specify the following.
  - A new abort stamp cause, `cleanup_uncertain`, routed in `handle_p426_incomplete` before the DNF-cause check.
  - A chain-side scan by session id, hermetic roots and container name, bounded by a deadline.
  - A hold state that does not need a live probe. It records an episode, keeps the leg PAUSED and holds until the designer resumes.
  - `PAUSED` blocks the next launch, so a live owned process cannot overlap it.

### F5 — `PASS_NO_INFLIGHT` is not accepted by the existing freeze and verdict consumers
- **Severity:** minor. **Evidence:** confirmed.
- **Location:** spec §4.3; `p426_freeze.py:215-219` (`inject_accepted`); `p426_wave2.py` (v8 positives rule).
- **Problem:** §4.3 names only the `p426_wave2` v8 rule. `inject_accepted` lists `PASS`, `DECLINED`, `PASS_BY_TRANSFER` and `WAIVED`. A `PASS_NO_INFLIGHT` entry would fail `cmd_v8_tg2` and the harvest. `m62/run_m62_live.py` results use verdict strings too.
- **Proposed change:** List every consumer of the verdict strings and add the new verdict to each: `inject_accepted`, `cmd_v8_tg2`, the harvest, the live-run `Result`. Add a red test that a record with `PASS_NO_INFLIGHT` freezes.

### F6 — The rerun-index bound in `validate_progress` is not addressed
- **Severity:** minor. **Evidence:** confirmed.
- **Location:** spec §5.6; `chain_rows.py:206-213`, `396-409`.
- **Problem:** §5.6 says harness reruns are "separate from `MAX_RERUNS`" and that fault-then-cheat and cheat-then-fault each use their own cap. `validate_progress` fails any `rerun_index > MAX_RERUNS` and requires `exhausted` only at index `MAX_RERUNS`. A fault rerun plus cheat reruns can reach index 3.
- **Proposed change:** Either state that P426 has no cheat rerun (so the maximum index is 1), or raise the bound and adjust the `exhausted` rule. Add one test for the combined case.

### F7 — A denied start-order or liveness read still routes a foreign daemon to `uncertain`
- **Severity:** minor. **Evidence:** hypothesis.
- **Location:** spec §3.2; `proc_guard.py:1086-1101`, `1095-1097`.
- **Problem:** §3.2 handles only denied cwd and environ reads. The first reads in the cleanup loop, `_protected` (start order) and `_live_denied`, call `_note_unreadable` before any ownership test. The reconcile step then resolves the process "unresolved" and marks cleanup uncertain. A system daemon denied at that stage does not reach the new test order.
- **Proposed change:** Apply the unclaimed-and-denied rule to those reads too. If the process is not claimed by tracked ancestry or session, it goes to `foreign_new unreadable`. Keep `uncertain` only when ancestry or session claims it, or when the session id itself is unreadable.

### F8 — A kept accounting-fault item continues without a settle check
- **Severity:** minor. **Evidence:** hypothesis.
- **Location:** spec §5.2.
- **Problem:** §5.2 says no state carries to the next item. A count mismatch can be a signal that a generation is still running on the worker, since cancel evidence is weak (see `cancellation_consistent`). `handle_p426_incomplete` checks `in_flight == 0` before it continues. §5.2 has no such check.
- **Proposed change:** Require worker `in_flight == 0`, same identity and router owner before `.continue` on an `accounting_fault`. A failure there is integrity (hold or invalidate), not a flag.

### F9 — §12 push binding
- **Severity:** minor. **Evidence:** confirmed for the code context, hypothesis for consequences.
- **Location:** spec §12; `local_gate.py:512`, `661-685`, `758`.
- **Problem:**
  - The spec says "the four protected paths" and "the tg1 carrier JSON" without giving paths. The red tests cannot be written from this text. tg2 may have its own carrier.
  - `push_level` obtains the receipt only as a name (`pass_receipt` returns a name). The spec does not say where `pushed_base` is read from, nor how an old receipt without it is handled beyond "refused".
  - `git diff <pushed_base> <remote>/main` must fail closed when `pushed_base` is not in the repo (a gc'd or rewritten history). The spec says only "empty".
  - No rationale is given for why comparing the old base with the moved remote protects anything. For a fast-forward push, local contains the remote changes and the gate already ran on the full tree. For a force push it is irrelevant. State the hazard it covers.
  - The check should run only for non-evidence pushes at level `full`, which the placement implies. Say so, since `docs-only` and `data-only` return earlier.
- **Proposed change:** Name the paths as a constant in `local_gate.py`. Read `pushed_base` from the receipt document through one helper, and refuse on any git error. Add a red test for a missing base commit and one for a non-`main` pushed ref. Add the one-line rationale.

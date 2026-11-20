**Round 1 of 3 findings on `docs/specs/s27-harness-robustness.md` v1.0.** Nothing was modified.

I read the spec in full and traced it against the code. I did not trace `p426_hooks.py`, `chain_hooks.py` beyond the disposition kinds, `p426_harvest._inventory`, or `p426_wave2.classify_leg` and the watcher. P11, P12 and P13 are therefore untraced or only partly traced, as noted in each.

**Driver's assumptions:**

| # | Assumption | Verdict |
|---|---|---|
| 1 | session id == `probe_session` is a sound ownership test | Holds only for a chain-launched probe (P5) |
| 2 | `kill_boundary_late_record` accepts only the benign order | Too narrow, not too lax (P4) |
| 3 | Retry builds on the existing slot / rerun machinery | False for tg1/tg2 P426 legs (P1) |
| 4 | The order-tolerant causal rule still proves the stop path | No, for the no-request-in-flight case (P6) |
| 5 | HOLD trips neither the 300 s barrier timeout nor the idle cancel | Holds, with caveats (P9) |

### P1 — The P426 chain has no rerun machinery to build on
- **Severity:** major. **Evidence:** confirmed.
- **Location:** spec §5.2 and §10; `chain_core.py:2576-2596`, `2922-2923`, `2495-2498`, `2370-2386`; `chain_rows.py:206-213`, `370`, `394-409`; `chain_core.py:1467`; `chain_hooks.py:13-16`.
- **Problem:** The spec says the retry builds on the existing slot / rerun machinery. That machinery exists only in `run_block_leg`, the per-arm layout (`pending_reruns` becomes a `kind="rerun"` invocation with `rerun_index`).
  - `run_p426_leg` builds steps with no `rerun_index` and aborts on any result other than `ok` or `dnf`.
  - `pump_barrier` raises `ChainAbort("… no same-slot re-run (tg2 step)")` for any non-accept disposition when the config is not per-arm.
  - A rerun launched from `run_p426_leg` would reuse `rerun_index=0`, so `load_slots` fails with "duplicate slot … re-run index 0".
  - `MAX_RERUNS=2` and the `exhausted` / `cheat` rules in `validate_progress` and `load_slots` share the rerun index. A harness-fault attempt gets `last.disposition` not in {accepted, exhausted, cheat}, so it falls into `table.blocked` instead of a pending rerun.
  - `accept_invocation` returns `"hook"` for `hold` and `harness_fault`, and `run_p426_leg` turns that into a ChainAbort.
- **Scenario:** A reconcile fault on item 5 is dispositioned `harness_fault`. The chain aborts with "the invocation ended 'hook'", or the leg is marked blocked. The leg is invalidated, which is the outcome the spec is meant to prevent.
- **Proposed change:** Add a section specifying the following.
  - A rerun mode in `run_p426_leg` that takes `rerun_index` from the slot table.
  - `pump_barrier` accepting `harness_fault` and `hold` in P426 mode.
  - Entries in `SLOT_DISPOSITIONS` and in the `load_slots` branches.
  - A decision on whether harness reruns share or are separate from `MAX_RERUNS`, including the interaction of cheat-then-fault and fault-then-cheat.
  - How the ledger check at `chain_core.py:1467` treats the extra attempts.
  - Cache-session reset before the rerun. The cheat path resets it (`chain_hooks.py:6`) and `recover` does too, but §5.2 says "immediately" and does not mention a reset. A warm prefix cache from attempt 1 changes TTFT, and possibly numerics, on the rerun.
  - A settle check before the rerun: worker `in_flight == 0` and the same worker identity, as `handle_p426_incomplete` does for a DNF.

### P2 — The retry trigger is outcome-conditioned, which biases the A/B comparison
- **Severity:** major. **Evidence:** confirmed structurally; the effect size is a hypothesis.
- **Location:** spec §5.1–5.2; `p426_reconcile.py:486-511` (`killed` / kill cases).
- **Problem:** Reconciliation faults of the D1 family arise only on items the gate killed (loop, stall, budget, ceiling). Those are the failing, non-converged items. The race window scales with per-request timing, which differs by arm (predictor ON vs OFF decode speed, ingest lag).
  - Rerunning "same seed" is not deterministic in an agentic loop. For a looping item it is a second draw at an outcome that was already bad.
  - Both arms follow the same rule, but the fault probability differs per arm, so the rerun rate differs per arm.
  - A second fault becoming a strict-fail DNF is the mirror image of the same asymmetry.
- **Scenario:** The arm with slower ingest has more kill-boundary faults. Its looping items get a free second draw, so its `acc_strict@budget` is biased upward relative to the other arm.
- **Proposed change:**
  - Pre-register per-arm fault and rerun counts as reported fields.
  - Pre-register a sensitivity analysis that scores harness-fault items as missing in both arms of the pair.
  - Keep attempt 1's gate outcome (`stop_reason`, `nonconv_kind`) in the attempt record.
  - Prefer making the fault surface smaller (P4) over retrying it.
  - Scope request: state a per-arm bound on harness-fault reruns (not only ≤3 DNFs per leg) beyond which the designer reviews.

### P3 — An uncertain owned cleanup plus an immediate rerun removes a protection
- **Severity:** major. **Evidence:** confirmed.
- **Location:** spec §5.1 ("owned-cleanup `uncertain` for that item"), §3.2, §3.4; `arm_runner.py:845-860`; `chain_core.py:2598-2612`, `2639-2643`.
- **Problem:** `uncertain` means a tracked or owned process was not verified gone: an agent client that may still be issuing requests, or a Gradle or node daemon holding CPU.
  - Today that blocks any retry (`require_certain_cleanup`, `p426_dnf_eligible`).
  - The spec reruns the item immediately with no re-verification.
  - An uncertain cleanup raises `TransportAbort` from `guard.cleanup()`, so there is no row and no `done` barrier. The abort stamp has no DNF cause, and `handle_p426_incomplete` calls it systemic.
  - The spec does not say how this path reaches `harness_fault`.
  - It also leaves open whether non-empty `survivors` or `containers_remaining` count as harness faults. §3.4 excludes them from "certain", and §5.1 does not say.
- **Scenario:** A surviving owned process from attempt 1 keeps decoding against the worker while attempt 2 runs. Attempt 2's latency and token accounting are contaminated, and the chain accepts it.
- **Proposed change:**
  - `uncertain` becomes a harness fault only after a second, independent cleanup scan returns certain with `survivors` and `containers_remaining` empty.
  - The worker must show `in_flight == 0` and an unchanged identity.
  - Anything else stays systemic or invalidating.
  - Specify the abort-manifest route (a new stamp cause or a new branch) explicitly.

### P4 — `kill_boundary_late_record` is too narrow, with an unclear offset direction
- **Severity:** major. **Evidence:** confirmed for the code paths; the D1 timeline is read from the open-questions text.
- **Location:** spec §4.1–4.2; `arm_runner.py:495-529`; `token_turn_gate.py:275`, `437-449`; `p426_reconcile.py:322-348`.
- **Problem:**
  1. `requests_at_kill` is read at `arm_runner.py:503`. The metrics HTTP GET follows at `:512`. `capture_cutoff` (`:523`) comes after `graceful_stop`'s full-process `tick()`. A step the client records inside that window is the benign case. Its `step_finish` offset can be below `signal_offset`, because bytes written earlier but ingested later are pre-signal. The spec requires the nth `step_finish` offset ≥ `signal_offset`, so it accepts only a step written after SIGTERM and rejects the in-window order. D1's text ("before the client recorded the step") is ambiguous on which one occurred. Ask the designer to confirm from the `sgf-parsing` events file which side of `signal_offset` the 26th `step_finish` is on.
  2. The rule requires "no failed line". A loop or stall stop normally lands while the client has already started the next request. That gives `|C| == expected+1` plus one trailing failed line, and `p426_reconcile.py:336` still rejects it.
  3. `signal_offset` is `None` when no SIGTERM was delivered. The rule then does not apply and the item faults and reruns, which is P2's bias again.
  4. The worker-count window {expected, expected+1} adds almost nothing, because `worker_deltas` already ties `|C|` to the post-kill delta.
- **Proposed change:** Record `events_size_at_count`, the file size when `requests_at_kill` is read. Accept the late record when the nth `step_finish` offset is ≥ that size (this covers both orders). Add the trailing-failed variant explicitly, with its own test. State the `signal_offset=None` outcome.

### P5 — Session-id ownership kills an unrelated session when the guard is not in an isolated session
- **Severity:** major. **Evidence:** confirmed for the code; the failing launch route is a hypothesis.
- **Location:** spec §3.1–3.2, assumption 1; `proc_guard.py:374`, `836-842`; `benchmark/m62/universe_preflight.py:67`; `arm_runner.py:353-356`.
- **Problem:** `probe_session = os.getsid(0)` is whatever session constructs the guard. It equals the probe's own pid only for a chain-launched probe (`chain_core.py:2055`).
  - The spec removes the `_sweep_excluded` skip, so same-session untracked young processes are SIGKILLed at cleanup.
  - A hand-run probe or preflight, or tests, from a terminal tab puts the operator's other jobs and tools in that session. They are killed at cleanup if they started after the guard.
  - Path-only attributed processes (cwd or argv under a guard root) change from "uncertain, refuse" to "kill". That reaches an operator `tail -f`, `rg` or editor on a work or run directory.
- **Proposed change:**
  - Treat the session as ownership only when `os.getsid(0) == os.getpid()`, or when the chain passes the session id explicitly, for example via an env var recorded in the manifest. Otherwise ownership is tracked ancestry only.
  - Kill path-only matches only with corroboration: the run's `HOME` / `XDG_*` in the environment, a tracked ancestor, or session membership. Otherwise record them as `foreign_new` with `path_match: true`.
  - Specify the kill-and-verify loop for non-tracked owned processes. The code has one only for `tracked`.

### P6 — The "no request in flight" causal relaxation turns a not-observed into a PASS and proves nothing about cancellation
- **Severity:** major. **Evidence:** confirmed for the code; the failure scenario is a hypothesis.
- **Location:** spec §4.3; `inject_verify.py:175-199`; `arm_runner.py:511-514`.
- **Problem:** Today a kill that lands after the in-flight message settled returns `not_observed:trailing`, so the positive is retried or declined. The spec makes it PASS with a recorded order. A stop path whose cancel does not interrupt generation would pass.
  - `in_flight_at_kill` is sampled before SIGTERM (`:512`). A request can start in between, giving `in_flight_at_kill == 0` with an interrupted trailing message.
  - §4.3 does not say whether the loop kind's `sleep 600` descendant-kill check (`:190`) stays.
  - The reference arm's C366 transfer relied on in-flight evidence.
- **Proposed change:**
  - Use `no_request_in_flight` only when all of the following hold: `trailing` is not an interrupted kind, worker `requests_started` is unchanged from before to after, `after.in_flight == 0`, and the `cancel_wait_s` bound holds.
  - Otherwise use the existing proof.
  - Keep the descendant check for `loop`.
  - Mark such a PASS with a distinct verdict so stage-3 consumers can tell it from a cancellation proof.

### P7 — `foreign_new`, recording, and the speed-invalid tiers have no per-item persistence
- **Severity:** major. **Evidence:** confirmed.
- **Location:** spec §3.3, §8.3; `arm_runner.py:856`, `1223`, `1287`, `1293-1294`; `chain_core.py:2176`.
- **Problem:** `ctx["cleanup_status"]` is overwritten by each item. It reaches the manifest only at a hook stop or an abort, and the chain reads it only from the final manifest. Rows carry `orphans_unattributed` and nothing else.
  - For a normally completed item, the `foreign_new` list, any killed-owned escapees, and the cleanup tier inputs are lost.
  - `classify_leg`'s speed-invalid and record tiers (§8.3) cannot be computed from the recorded data.
- **Proposed change:**
  - Persist each item's `cleanup_status` (`foreign_new` and killed-owned entries included) in the row, or in a sealed per-item record keyed by slot.
  - Add it to the row schema and the identity.
  - Have the `done` hook (and so P3's decision) read it.

### P8 — A denied read on a young foreign daemon still makes cleanup uncertain
- **Severity:** major. **Evidence:** confirmed in the code; occurrence on macOS is a hypothesis.
- **Location:** spec §3.1 (adds environ and session reads); `proc_guard.py:1086-1141`, `1010`, `1031-1045`.
- **Problem:** `_attributed_path` calls `p.cwd()`, and the new environ read is also routinely denied for hardened system processes on macOS. A denied read leads to `_note_unreadable`, then `_resolve` returning "unresolved", then `uncertain=True` with reason "unreadable record unresolved" or "identity unreadable". D2's fix only covers the readable case. The same daemon (`helpd`, `mdworker_shared`) can still invalidate the leg through the unreadable route, and the spec adds more denied reads.
- **Proposed change:** Order the tests: tracked or ancestry, then `getsid` (nearly always readable for same-uid processes), then path or environ. A young process in a foreign session whose ancestry does not reach a tracked pid and whose path or environ reads are denied is recorded as `foreign_new` with `unreadable: true`, not uncertain. Keep uncertain for denied reads on a tracked-ancestry or same-session process. Add a red test for it.

### P9 — HOLD: the assumption holds, but two cases are unspecified
- **Severity:** minor. **Evidence:** hypothesis for the idle-eviction case.
- **Location:** spec §8.2; `arm_runner.py:46`, `1285-1289`; `p426_wave2.py:1106-1120`.
- **Problem:**
  - The `.stop` path exits the probe at once, so the 300 s ACK timeout does not apply. The chain's idle cancel lives in `supervise` and does not run while no probe is up. The overrun file never kills. That part of assumption 5 holds.
  - A long hold can outlast worker or router idle eviction or the cache-session lifetime. The resume then fails the worker-identity check, or silently changes the cache state. Nothing re-verifies the worker, router and `:8000` ownership on resume.
  - `hold` currently falls into `accept_invocation`'s "retry" branch and returns `"hook"` (see P1).
- **Proposed change:** On resume, re-run the leg-entry checks (worker identity, router owner, AC power, no other GPU job) before the next invocation. Record the cache-session state at hold and resume. Reuse the existing `PAUSE` file at `wait_boundary` where possible, so there are not two pause mechanisms.

### P10 — The cleanup receipt schema change breaks existing consumers
- **Severity:** minor. **Evidence:** confirmed for the validator; the consumer list is partly a hypothesis.
- **Location:** spec §3.4; `chain_incident.py:15-16`, `40-56`; `chain_core.py:2464-2465`.
- **Problem:**
  - `cleanup_problems` requires the exact key set. Prior chain.json and manifests, including the failed leg `tg2-m76-n16-s1.a1` that §10.2 harvests, lack `foreign_new` and now fail "not the exact schema".
  - `CLEANUP_LISTS` still requires `orphans_unattributed` to be empty. The spec says it may be non-empty and does not say the validator must stop requiring that.
  - The spec's "certain and complete" formula drops the `unknown` emptiness check.
  - `foreign_new` is unbounded.
- **Proposed change:** Version the receipt (`schema: 2`). Accept the old schema for old identities, for harvest and freeze reads. Remove `orphans_unattributed` from `CLEANUP_LISTS`. Keep `unknown` empty in the certain definition. Cap `foreign_new` (for example 64 entries plus a count) and restrict it to non-descendant young processes with `ppid == 1`.

### P11 — C365: the abort path can block and can start a queued grade
- **Severity:** minor. **Evidence:** confirmed for the code; the failure scenario is a hypothesis.
- **Location:** spec §6; `arm_runner.py:839-860`, `210-258`.
- **Problem:**
  - After `kill_role("grader")`, `worker.finish()` joins for up to `join_timeout_s` (`2*max timeout + overhead`) and can start a queued next capture before cleanup.
  - Reclassifying a failure as `grade_cancelled` could also swallow a grader fault that predates the abort.
- **Proposed change:** The cancel mark must also clear `queued` and stop dequeuing. Set it only when the primary exception already exists. A failure stored before the mark stays raised or recorded as a fault. State the join bound for the abort path.

### P12 — D3 and C368 details
- **Severity:** minor. **Evidence:** hypothesis (I did not read `p426_harvest._inventory`).
- **Location:** spec §7.
- **Problem:**
  - The recorded `link` target of an excluded symlink can be an absolute path with the home directory in it. The inventory is public-bound, and AGENTS.md forbids absolute home paths.
  - `package-lock.json` is omitted only at the root. Rust omits every `Cargo.lock` outside the prepared tree.
- **Proposed change:** Record the link target through the portable scrubber, or only its basename and a hash. Omit any `package-lock.json` not in the prepared tree, matching the Rust rule, and add a nested-lock case to the red tests.

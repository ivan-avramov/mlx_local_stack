# Implementer report: S27 robustness bundle, fix round 2 (ledger Y1–Y6; review r2 of 3)

Working tree = candidate 2 (INDEX) + frozen tests + the edits below. I did not unstage, reset or commit anything. The raw
`change-verify-*-r2.md` reviews were not under `docs/reviews/s27-robustness/` or in scratch, so I worked from the ledger's
"why" column only.

## Per finding

| id | change | red test(s) in `test_s27_impl_r2fix.py` | candidate 2 → after |
|---|---|---|---|
| Y1 | `p426_reconcile.py:394-395` `_open_step_at_signal` returns None unless `late["in_flight_at_kill"]` is an `int` (`type is int`, so bool is excluded) equal to 0 | `test_y1_..._never_stands_in_for_a_missing_or_malformed_sample[absent/None/bool/str/float]`; control `test_y1_the_anchored_case_holds_when_the_sample_read_integer_zero` | 5 FAILED (`rep.ok is True`) → pass; control passed on both |
| Y2 | `structured_grade.py:398-400`: a Go docker launch `OSError` is `GraderInfraError(kind="spawn")`; Python keeps the plain `TransportAbort`. `proc_guard.py:1054-1069` `container_oom` is tri-state: `TimeoutExpired`/`OSError`, rc≠0, or stdout not `true`/`false` raise `GraderInfraError(kind="transport")` | `test_y2_a_docker_launch_oserror_is_a_typed_spawn_fault`; `test_y2_an_unverifiable_oom_inspection_is_a_transport_fault_never_not_oom[rc1/empty/garbage/timeout/oserror]`; controls `..._python_interpreter_oserror_stays_an_untyped_abort`, `..._verified_oom_inspection_reads_its_state[true/false]`, `..._unverified_oom_state_never_scores_the_item` | 6 FAILED → pass; controls passed on both |
| Y3 | `chain_ops.py:1002-1016` `owned_scan`: before claiming any member, read the start of the live process whose pid == sid. If it is not the recorded probe (start ≠ `not_before`): no session claim, recorded as `session_reused={pid, create_time, probe_started}` (`:1110`, docstring `:988-990`). If the leader has exited (NoSuchProcess): members are claimed, bounded by the start as before. If the leader is unreadable: a problem is added (scan uncertain) and nothing is claimed | `test_y3_a_reused_session_whose_leader_is_not_the_recorded_probe_is_never_claimed`; `test_y3_an_unreadable_session_leader_leaves_the_scan_uncertain_and_claims_nothing`; `test_y3_the_recorded_probe_leading_its_session_is_still_claimed` | 3 FAILED → pass. The third failed on candidate 2 only on the new `session_reused` key; it is the positive control |
| Y4 | One validator, `p426_hooks.py:92-120` `accounting_problems(doc, slot, rindex, *, row, item_record, recorded)`. It requires: sealed; `disposition == "accounting_fault"`; same slot; `rerun_index` an int equal to the attempt's; `row_sha256` equal to the committed row's (a missing row fails); `item_record_sha256` equal to the item record's, or None only when `failed_checks == [r]` for a recorded failure `r`. Helpers `recorded_accounting` / `ledger_invocation` / `row_for_slot` (`:123-145`). Used by: the chain (`accounting_sealed_for` `:148-167`, which now also reads `items/<slot>.json`; `chain_core.py:3266-3269` passes the failure in hand plus this slot attempt's earlier `p426_accounting` reasons), freeze (`p426_freeze.py:413-432`, `ledger_row` + `_accounting_problems` `:444-466`, replacing `_accounting_ok`), and harvest (`p426_harvest.py:701-728` `_accounting_problems` from inventoried files, called at `:765-769`) | `test_y4_freeze_and_harvest_refuse_a_sidecar_that_does_not_bind_the_slot_attempt[no-record-unrecorded/unnamed-unrecorded/other-row/other-slot/other-rerun/other-disposition/other-record]`; `test_y4_the_one_validator_is_used_by_the_chain_freeze_and_harvest`; `test_y4_the_chain_counts_an_existing_sidecar_of_its_own_recorded_failure_as_written`; controls `test_y4_a_sidecar_bound_..._is_accepted_by_freeze_and_harvest[names-its-record/no-record-recorded-failure/record-unnamed-recorded-failure]` | 9 FAILED → pass; controls passed on both |
| Y5 | `arm_runner.py:1002-1008` new `_record_finish(worker, termination, scrub)`. It is used on the main path (`:777`, behaviour unchanged) and on the unwind's non-aborting join (`:957`, which used to drop the return value). It uses `setdefault`, so a fault already recorded is never overwritten | `test_y5_a_returned_interim_infra_fault_is_recorded_on_every_join_path` (the helper's behaviour, plus a source check that `_run_item` has no bare `worker.finish()` and calls the helper on both paths) | FAILED (no helper) → pass |
| Y6 | `proc_guard.py:45` `FOREIGN_ARGV0_CAP = 64`; `:915-917` the `foreign_new` basename is scrubbed first, then capped at 64 characters | `test_y6_a_foreign_new_basename_is_capped_at_64_characters[long path basename / title-style argv0]` | 2 FAILED → pass |

How I got the red runs: I saved the source edits to `../scratch/r2fix-src.patch`, restored the nine source files from the INDEX
(`git checkout -- <files>`, working tree only), ran the new file (26 failed, 8 passed), then re-applied the patch by hand.
`git diff` of the nine files then matched the saved patch byte for byte (`cmp`: IDENTICAL).

## Files changed

- `benchmark/bench/p426_reconcile.py`: Y1, the anchored case requires an integer-0 sample.
- `benchmark/bench/structured_grade.py`: Y2, a Go docker launch `OSError` is typed `spawn`.
- `benchmark/bench/proc_guard.py`: Y2 tri-state `container_oom`; Y6 basename cap.
- `benchmark/bench/chain_ops.py`: Y3, leader-identity guard and `session_reused` in the scan result.
- `benchmark/bench/p426_hooks.py`: Y4, the shared validator and its helpers; `accounting_sealed_for` built on it.
- `benchmark/bench/chain_core.py`: Y4, passes the recorded failures to `accounting_sealed_for`.
- `benchmark/bench/p426_freeze.py`: Y4, uses the shared validator; `_accounting_ok` removed; `import os`.
- `benchmark/bench/p426_harvest.py`: Y4, validates the inventoried sidecar with the shared validator.
- `benchmark/bench/arm_runner.py`: Y5, `_record_finish` used on both join paths.
- `benchmark/bench/tests/test_s27_impl_r2fix.py`: new, 34 tests.
- `benchmark/bench/tests/test_s27_impl_r1fix.py`, `benchmark/bench/tests/test_s27_impl_scan.py`: edits listed below.

## Edits to existing tests

- `test_s27_impl_r1fix.py::test_x4_this_attempts_own_sealed_sidecar_counts_as_written_and_the_leg_continues` (`:94-96`), clause
  Y4. The pre-existing sidecar named no item record and carried an unrecorded failure (`["boundary_count"]`); Y4 refuses
  exactly that. The sidecar now names a sealed item record written beside it, which is the hook-written case. The test still
  asserts the leg continues.
- `test_s27_impl_r1fix.py::_fake_table` (`:669-670`), clause Y3. The fake process table now reports the session leader pid 5150
  as exited (`NoSuchProcess`). Without this, the result depended on whether a real pid 5150 existed on the box: Y3 reads the
  leader's identity, and a live real pid 5150 would read as a reused session.
- `test_s27_impl_scan.py::test_the_second_scan_kills_and_verifies_a_survivor_of_the_probe_session_and_spares_a_foreign_one`
  (`:35-37`), clause Y3. The spawned session leader stands for the probe, so `not_before` is now its own start, not the test
  process's. Before, the leader was not the recorded probe, which is exactly the reuse case Y3 refuses to claim.

## Commands and results (all via `../fe_test.sh stack …`; paths relative to `benchmark/`)

- `bench/tests/test_s27_impl_r2fix.py` on candidate-2 sources: 26 failed, 8 passed (failures listed per finding above). After:
  34 passed.
- All `test_s27_impl_*` (chain, gate, guard, harvest, positives, r1fix, r2fix, reconcile, runner, scan, watch): **242 passed**.
- Frozen `test_s27_fe_*` (chain, done_hook, grader, harvest_view, offsets, ownership, positives, push_binding, reconcile,
  support): **7 failed, 202 passed**. The 7 are the known conflicts the test-writer is amending:
  - `test_s27_fe_done_hook.py::test_the_recorded_d1_item_is_reconciled_by_the_hook_and_the_item_record_carries_the_late_record` (X9)
  - `test_s27_fe_reconcile.py::test_d1_the_recorded_numbers_are_a_late_record_of_the_unpublished_order` (X9)
  - `test_s27_fe_reconcile.py::test_d1_the_offsets_are_recorded_but_not_required_for_the_unpublished_shape` (X9)
  - `test_s27_fe_grader.py::test_two_final_infrastructure_faults_then_a_pass_is_accepted_with_one_generation_and_one_snapshot` (X6)
  - `test_s27_fe_grader.py::test_one_final_infrastructure_fault_then_a_fail_is_the_models_scored_fail` (X6)
  - `test_s27_fe_grader.py::test_three_final_infrastructure_faults_end_the_item_with_the_grader_infra_stamp_and_the_generation_evidence` (X6)
  - `test_s27_fe_grader.py::test_an_interim_grader_infrastructure_fault_ends_the_probe_before_any_outcome_with_the_typed_stamp` (X6)

  Verbatim: D1, `AssertionError: ['boundary_count: |C|=26, len(request_usage)=26, the evidence states 25']` (the frozen row has
  no open-step id, X9); grader, `TransportAbort: docker command failed: Cannot connect to the Docker daemon (grader
  infrastructure)` (untyped fixture, X6). I did not re-run the frozen set on candidate-2 sources. I matched these to the known
  seven by count and by cause; none of them touches code changed in this round.
- Existing tests of the touched modules, one invocation per family:
  - proc_guard (`test_proc_guard`, `test_c157_proc_guard`, `test_g1_round2_proc_guard`, `test_p585_proc_guard_systemerror`,
    `test_c151_start_time`): 149 passed.
  - structured_grade (`test_structured_grade`, `test_c147_grade_reports`, `test_p604_go_package_load`, `test_m62_revision5`,
    `test_tg1_runner`, `test_tg1_integration`): 143 passed, 6 skipped.
  - chain_ops (`test_chain_ops`, `test_m64_chain_ops`): 143 passed.
  - chain_core (`test_p371_chain_core`, `test_b2_s3_core`, `test_m64_chain`, `test_b2_s8c_chain`, `test_b2_fix_chain`): 207 passed.
  - p426_reconcile (`test_b2_s4_reconcile`, `test_b2_frozen_s4_reconcile`, `test_p586_impl_reconcile`,
    `test_p586_fix_reconcile`, `p586_frozen/test_p586_reconcile`): 241 passed.
  - p426_hooks (`test_p586_impl_hooks`, `p586_frozen/test_p586_hooks`, `test_p371_m64_hooks`): 39 passed.
  - p426_freeze (`test_b2_s8_freeze`, `test_b2_frozen_s8_freeze`, `test_p586_fix_freeze`, `test_b2_fix5`, `test_b2_s8_wave2`):
    236 passed.
  - p426_harvest (`test_p426_harvest`, `test_b2_s9_harvest`, `test_b2_frozen_s9_harvest`, `test_p586_impl_harvest`,
    `test_p586_fix_harvest`, `p586_frozen/test_p586_harvest`, `test_s26_kv_rehearsal_harvest`): 252 passed.
  - arm_runner (`test_c147_cancel`, `test_c147_chain_runner`, `test_c147_inject`, `test_m62_v5a`, `test_m62_safety`): 214 passed,
    4 skipped.

  All 10 skips: `bench opencode 2.0.20 not installed (scripts/install_bench_opencode.sh)`. No module family had a failure, so
  there is no failure carried over from candidate 2 to name.
- I ran no full suite, server, model, GPU, docker or benchmark leg.

## Not satisfied or open

- No finding is left open.
- The test-file glob matched 165 test files that import a touched module, which is close to the whole suite. I ran each
  module's direct test family (listed above), not all 165. Y9's full-suite gate is still the operator's check.
- `chain_ops.owned_scan`'s `path_only` entries record the same argv[0] basename as `foreign_new` but stay uncapped. Y6 names
  `foreign_new` only, so I did not change them. Question for the lead: cap them too, using the same constant?

## Choices made

1. Y1: a float `0.0` is refused as well. The sample is recorded as an integer count; `type is int` matches the existing
   `_is_int`.
2. Y2: only the Go branch types a launch `OSError`. A missing Python `.venv-bench` interpreter stays a plain `TransportAbort`,
   because a regrade cannot fix it and the ledger scopes Y2 to docker. The tri-state check lives in `ProcessGuard.container_oom`
   (where the "unverified reads as not OOM" fallback was) and mirrors tg2's `_container_oom`.
3. Y3: when the leader pid is gone, members are still claimed, bounded by the probe's start. The kernel does not reuse a sid
   while any member lives, so a member there is the probe's. An unreadable leader is uncertain (PAUSED), never claimed. A reuse
   is recorded and not refused (`certain` stays True), as the ledger says ("no session claim (recorded)").
4. Y4, "recorded done-hook failure": the sidecar's `failed_checks == [reason]` must match a reason chain.json's
   `p426_accounting_faults` recorded for that slot and rerun index. Both chain writers (the done-hook `HookInfrastructureError`
   path and the abort route at done with the outcome present) record exactly that. So the abort-route sidecar also counts as a
   recorded done-step failure.
5. Y4: a sidecar that names no item record while one exists is accepted only with a recorded failure. This is the case where
   the hook's sidecar write failed and the chain then sealed one; refusing it would refuse correct facts.
6. Y4, freeze: the no-item-record path now applies only when the record file is absent (`lexists`). A corrupt or unreadable
   item record is refused, never treated as "none written".
7. Y4: a missing committed row (`row_sha256` None) fails the contract everywhere, including in the chain's existing-sidecar
   check. Before, None == None passed.
8. Y4, chain: an existing sidecar counts as written when it binds this attempt's row and item record and carries the failure in
   hand or one this slot attempt already recorded (resume).
9. Y4, harvest: the row and the item record are read from inventoried regular files only (`_read_regular`, no symlinks
   followed), never from paths outside the inventory.
10. Y5: I factored out the helper so the unwind path is unit-testable. That path is hard to reach through `run_item`, so the
    test checks the helper's behaviour plus the source of `_run_item`.
11. Y6: scrub first, then cap, so a truncation cannot split a pattern the scrubber would have caught.

## Clarification (same session): Y6 extended, the faulted interim boundary, the frozen v3 set

### Results

1. **Y6 extended.** Done: the chain scan's `path_only` basename is now capped at 64 characters. Red → green.
2. **Faulted interim grade.** Done: when `GradeWorker.finish()` returns an interim infrastructure fault, it first discharges
   that capture's boundary as ungraded. Red → green.
3. **Frozen v3 set.** 1 failure remains:
   `test_s27_fe_r1.py::test_x10_a_session_member_started_after_the_probe_is_ours_and_is_killed`. That test conflicts with the
   adopted Y3; I believe the test is wrong under the ledger (details below). A second v3 failure came from my own over-strict
   Y4 reading; I fixed my code, not the test.

### Changes

- **Y6, `path_only` cap**, `chain_ops.py:1064-1067`. The `path_only` basename is capped with `pg.FOREIGN_ARGV0_CAP`. This site
  has no scrubber; the chain makes the scan result portable when it persists it (`p426_persist` → `portable_doc`), so the cap
  applies to the raw basename. A basename has no `/`, so a path-prefix scrub cannot be split by the cut.
  - Red test: `test_s27_impl_r2fix.py::test_y6_the_chain_scans_path_only_basename_is_capped_at_64_characters`, a real process
    with cwd under the root and a title-style argv[0].
  - Before: FAILED, the uncapped 222-character title. After: pass.
- **Clarification 2, faulted interim boundary**, `arm_runner.py:211` (`GradeWorker.grading`), `:268` and `:278` (set before a
  grade, cleared after `on_grade`), `:319-326`. When `finish()` returns an interim infrastructure fault, it removes that
  boundary from `gate.pending` and `gate.stall_wait` under the gate lock. No grade is recorded for it (`trajectory`
  unchanged). This happens only in `finish()`, after the client exited and before the terminal decision (`_run_item`: finish at
  `:788`, `gate.terminal` after the final grade). While the client still generates, the fault stays X3's pre-outcome harness
  fault (`check()` raises): discharging in the worker thread could let the stall rule fire first and turn a rerun into a
  scored stall.
  - Red test: `test_c2_a_faulted_interim_grade_returned_at_finish_leaves_the_terminal_decision_unchanged` (real
    `TokenTurnGate`, `no_progress_requests=2`, typed infrastructure fault at boundary 1).
  - Control: `test_c2_the_counterfactual_without_the_capture_stalls_at_the_terminal_decision`.
  - Before: FAILED, `1 not in {1}` (pending never discharged). After: pass. The control passed before and after.

### The frozen v3 set

The glob `benchmark/bench/tests/test_s27_fe_*.py` matches **11 files**, not the 12 the brief names: chain, done_hook, grader,
harvest_view, offsets, ownership, positives, push_binding, r1, reconcile, support. The 12th is missing or named differently. I
ran all 11.

- **First run: 2 failed, 267 passed.**
  - `test_s27_fe_r1.py::test_x4_a_sidecar_that_the_hook_already_sealed_for_this_row_is_not_written_twice_and_the_leg_goes_on`.
    **My fix was wrong; I changed my code, not the test.** Y4 allows "no item record" only when a done-hook failure is
    recorded. My first implementation went further: the sidecar's `failed_checks` had to equal the recorded reason text
    (round-2 choice 4). That text is descriptive. The binding that protects the data is slot / rerun index / row / item record
    / disposition, and all of it stays exact. Under S28-P5 ("simplest form that keeps the protection"), the reason match was
    surplus. `p426_hooks.accounting_problems` now requires only that a done-step failure is recorded for this slot attempt.
    For the chain that is the failure in hand, plus any earlier `p426_accounting` entry for the attempt. For freeze and harvest
    it is a `p426_accounting_faults` entry for (slot, rerun index).
    - Adjusted my own test `test_y4_the_chain_counts_an_existing_sidecar_of_its_own_recorded_failure_as_written`: a different
      reason now counts; no recorded failure, or another row, still refuses.
    - Reverted my round-2 edit to `test_s27_impl_r1fix.py::test_x4_this_attempts_own_sealed_sidecar_counts_as_written_and_the_leg_continues`
      to its original text; it was needed only because of the reason match. That leaves two edits to existing tests from this
      round: `_fake_table` and `test_s27_impl_scan`.
    - Freeze and harvest still refuse every case in `test_y4_…_refuse_…`, including "no record, nothing recorded" and
      "unnamed record, nothing recorded".
  - `test_s27_fe_r1.py::test_x10_a_session_member_started_after_the_probe_is_ours_and_is_killed`. **Under the ledger, the test
    is wrong, not the Y3 fix.** The test spawns a session leader (sid == its own pid) and records a probe start 10^6 s
    *before* that leader's start. It then expects the leader to be killed as a probe-session member. The probe leads its own
    session (`probe_session.sid` is the probe's pid, `started` its own start), so a live leader of that sid whose start is not
    the recorded probe start is exactly Y3's reused session. That is Sol P3's case: "an unrelated new session leader after the
    session died". Y3, as the lead adapted it, refuses to claim it ("a process with pid == sid that is not the recorded probe
    (create time) ⇒ the session was reused ⇒ no session claim (recorded)"). No version of the fix can satisfy both this test
    and Y3. The test predates Y3 and pins X10's start bound alone.
    - Suggested amendment for the test-writer: set `not_before` to the leader's own start (the leader IS the probe), or spawn
      a non-leader member inside the probe's session. The second shape is what X10(b) means.
    - Not edited (read-only).
- **After the Y4 change: 1 failed, 268 passed.** The one failure is the X10 conflict above, verbatim:
  `AssertionError: assert (None is not None)` (`leader.poll()`: the reused-session leader is not killed).

### Commands and results after these changes (`../fe_test.sh stack …`)

- `test_s27_impl_r2fix.py`: 37 passed.
- All `test_s27_impl_*`: 245 passed.
- Frozen v3, 11 files: 1 failed (above), 268 passed.
- Families touched in this clarification:

  | family | result |
  |---|---|
  | arm_runner + gate (`test_c147_cancel`, `test_c147_chain_runner`, `test_c147_inject`, `test_m62_v5a`, `test_m62_safety`, `test_m62_revision5`, `test_tg1_runner`, `test_tg1_integration`, `test_token_turn_gate`) | 385 passed, 10 skipped (opencode 2.0.20 not installed) |
  | chain_core | 207 passed |
  | harvest | 252 passed |

  - I also ran chain_ops + hooks + freeze + harvest in one combined invocation: 641 passed and 29 errors. All 29 are
    `fixture 'kit' not found` in `p586_frozen/test_p586_harvest.py`, caused by collecting it alongside other families'
    files.
  - That file passes in its own family invocation (the harvest row above), and every non-harvest test passed in the combined
    run.

### Choices made in the clarification

1. The discharge happens in `finish()` only; X3's generation-time path is unchanged.
2. The discharged boundary is not recorded: no new `termination` field. The returned fault is still recorded as
   `interim_grade_fault`.
3. The Y4 reason match is dropped (see above). This supersedes round-2 choice 4.

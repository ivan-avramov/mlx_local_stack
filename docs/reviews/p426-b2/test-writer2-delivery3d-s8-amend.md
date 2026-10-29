All four parts of delivery 3d are done, and nothing was committed. On the baseline the support checks pass (55). On the s8 copy (before s8b / s8c) 90 failed and 375 passed; every failure has a class, and the only (d) left is one sequencer test (the watch journal's tick-time field, unpinned).

## 1–3. What I amended or added (all tagged `post-reveal 3d (§16.8)`)

**Fixtures**
- **`b2_frozen_add_support.SeqOps`:**
  - New seams: `operator_emails()` (emails passed in), `worktree_state(path)` (the v8 commit for the arm, clean, base gitlinks), `identity(path)` (v8's identity keys), `harvest_path(attempt)` = `<main-root>/benchmark/results/p426/wave2/<attempt>/`.
  - `historical_walls()` (`{w_python_s, w_go_s, max_request_elapsed_s}`): the sequencer's amendment goes through `p426_freeze` with these ops.
  - The fake harvest writes `HARVEST.json` inside `harvest_path`.
  - The constructor now takes `main_root=`, `emails=`, `walls=`.
- **`write_leg`:**
  - writes `<out-root>/schedule.json` in the `schedules.tg1` shape, and `chain.json.schedule_sha256` is its real sha;
  - every item-record request carries `elapsed_s`;
  - new knobs `status`, `shape`, `drop_slots`, `elapsed_s`.
- **`seq_argv`:** `rehearsal` gets `--frozen-prompt-date` (a test marker omits it).
- **`b2_frozen_support.occurrence`:** the last field is now `position` (0-based position in the frozen order).
- **The fake probe (`probe_main`):** applies `--inject-stall-item` / `--inject-stall-s`. That item becomes a boundary kill in the P371 golden `item_stall_kill` row shape.
- **New `b2_frozen_fix_support.Topology`** (§16.8 topology):
  - The real sequencer drives two P426 worlds under one `STACK_WORKDIR`.
  - A chain launch runs the real `run_tg1_chain.main(argv, ops=FakeOps)` on a thread.
  - A watcher launch runs the real `bench_watch.main` with its interval shortened.
  - Each handle is bound to a real helper process (`pid`, `default_create_time`).
  - Harvest and publication are recorded.
  - The clock advances the sequencer's waits.

**Tests touched or added**
| File | Tests |
|---|---|
| s0 | `test_the_occurrence_builder_has_the_five_fields_and_the_position` (renamed); **new** `test_the_stall_injection_uses_the_real_probes_stall_kill_row_shape` |
| add_support_check | `test_the_sequencer_fakes_write_a_leg_in_the_frozen_formats` (+ the §16.8 seams, `harvest_path`, the schedule sha, `elapsed_s`); `test_the_watcher_death_script_leaves_no_exit_state` (`main_root`) |
| s8 | `FreezeOps` + `identity`, `historical_walls`, `build_inputs` (`s2` per `EXPECTED_BUILDS`); new `MissingSeam`; `leg_root_with(…, elapsed_s)`; `_v8_argv(…, r1_elapsed_s)`; `makeup_groups…` rewritten (order by `occurrence`, de-duplication); **new:** `makeup_groups_ignore_the_input_order…`, `v8_derives_its_settle_bound…` ×3, `the_amendment_raises_the_settle_bound…` ×2, `v8_refuses_a_failed_production_tree_precondition…`, `a_missing_freeze_seam_is_a_refusal…` ×4 |
| add_sequencer | `seq()` (`main_root`, `emails`, rehearsal base); pilot-gate stops and invalid leg expect rc 1; operator email from `ops.operator_emails()`; dossier `harvest_sha256` from `harvest_path`; overrun = VALID + `overrun: true`, rc 3; make-up out-roots flat, occurrences compared by key; positions in the canonicalization test; rehearsal argv carries the date; **new:** `an_overrun_leg_the_operator_stopped…` (OVERRUN, never paired, rc 3), `a_failed_harvest_stops_with_4…`, `the_planned_slots_come_from_the_legs_frozen_schedule`, `a_slot_dnfd_in_both_arms_is_one_canonical_occurrence…`, `the_rehearsal_refuses_without_its_frozen_prompt_date` |
| fix_cases | R2 case: exact reason `reconciliation mismatch (injected)`, on the first item; **new:** `test_fix_p536_the_r3_stall_injection_kills_the_first_python_item_and_scores_it`, `test_fix_p536_topology_the_real_sequencer_runs_the_pilot_pair_through_the_real_chain`, `test_fix_p536_topology_one_makeup_leg_runs_through_the_real_chain` |

Both injections already refuse without `--rehearsal`, covered by the frozen s1 `test_new_rehearsal_injections_refuse_without_rehearsal` (which passes).

Two §16.8 points have no test of their own:
- **Production tree:** §16.8 doesn't say whether the `git diff` against the production ref is a `checks` precondition or run directly. I tested it as a precondition; the direct form needs a fork repo at the S′ gitlink, which a hermetic test can't create.
- **The rehearsal manifest's date and identity fields:** §16.8 says "the rehearsal manifest records it", but `p426_freeze rehearsal` takes no date flag. Please rule which command records them.

## 4. Runs

```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py bench/tests/test_b2_frozen_add_support_check.py
55 passed in 18.69s
../bin/run_stack_tests.sh <s8, add_sequencer, fix_cases>          102 failed, 2 warnings in 1.22s   (baseline has no s8 modules; no collection errors)
../bin/sync_to_s8.sh → 23 files;  ../bin/run_candidate_s8_tests.sh <the 20 set files> --tb=line -rf
90 failed, 375 passed in 125.35s
```

| Failures | Class | Evidence |
|---|---|---|
| s8 ×14: the rehearsal / v8 / derived-bound / production-tree tests, and the missing-seam cases `identity`, `historical_walls`, `build_inputs` | (a), P59 | `p426_freeze.py:253: no attribute 'restore_diff_problems'`: restore diff not through `checks` |
| s8 `missing_freeze_seam[worktree_state]` | (a), §16.8 | a missing seam ends in a traceback (`AttributeError: worktree_state`), not `REFUSED:` |
| s8 `amendment_raises…` ×2 | (a), P60 / P61 | `p426_freeze.py:469: KeyError: 'python'`: reads the old wall keys, not `w_python_s` / `max_request_elapsed_s` |
| add_sequencer ×20, fix_cases topology pilot (and the make-up case behind it) | (a), §16.8 | `IsADirectoryError … main/benchmark/results/p426/wave2/<attempt>`: the dossier hashes `harvest_path(attempt)` as if it were the `HARVEST.json` file; §16.8 pins it as the directory |
| add_sequencer `rehearsal_runs_r1…` | (a), §16.8 | no rehearsal leg launched: `--frozen-prompt-date` is not a `rehearsal` flag yet |
| add_sequencer `a_speed_valid_leg_records_it` | **(d)** | `speed_valid is True` fails. The s6 `speed_verdict` needs a numeric tick time `t`; my fake journal writes `at` only. The tick-time field is still unpinned (3c P52). |
| fix_cases R3 stall | (a), chain-side P536 (s1 / s3) | no probe invocation got `--inject-stall-item` |
| fix_cases make-up mode, R2 injection | (a), chain-side P536 (s1 / s3) | the chain refuses `makeup`; the R2 injection is not applied |
| s7 DNF ×7, add_ledger, fix_cases R3-limit / P23 | (a), queued | the flat-layout DNF defect |
| s7 smoke shape | (a), s1 | §16.3 shape not applied |
| fix_cases P510 ×5 | (a), queued | the s6 watcher crash |
| s0 ×2 | (c), baseline-only by design | base goldens / baseline argv |
| s9 ×25, add_scrub ×3 | (b) s9 | harvest `wave2`, `publish_*`, `Scrub(emails=)` absent |

**Which (a) the s8b / s8c fixes should clear:**
- P59: the 14 restore-diff tests.
- P60 / P61: the 2 amendment tests, plus the 3 v8 derived-bound tests once P59 no longer masks them.
- The §16.8 seams, `harvest_path` as a directory, `--frozen-prompt-date`, missing-seam refusal: 20 + 1 + 1 + 1.
- P62's production tree is under the same P59 mask.
- P63 (plan from the frozen schedule) is tested by `the_planned_slots_come_from_the_legs_frozen_schedule`, which is currently masked by `harvest_path`.

**Already satisfied on this copy:** both OVERRUN tests (VALID + `overrun: true` with rc 3, and the operator-stopped OVERRUN, never paired, rc 3) and the rc-4 harvest-failure test pass.

The chain-side P536 items stay red until s1 / s3: make-up mode, R2 / R3 injections, the smoke shape, and therefore both topology tests.
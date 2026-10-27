All four parts are done; nothing was committed. On the baseline the support checks pass (54); the frozen set gives 372 failed, 10 passed. On the fixed copy, 108 of 405 tests fail: 2 are my two now-amended defects, 2 are baseline-only s0 checks, 7 are the queued flat-layout DNF defect, 1 is a new finding, 3 are §3 entry checks the fix runs only after the router starts (unclear whether s7 owns them), and the rest are slices not built yet (s6–s9 and the sequencer).

## 1. Amendments (rulings 1 and 2)

| Ruling | Change | Tests touched |
|---|---|---|
| 1. Seal test | `test_b2_frozen_s5_receipt.py::test_new_a_receipt_whose_seal_does_not_verify_is_a_problem` now has 4 cases: seal replaced, or a volatile value edited without re-sealing, on either receipt. Each asserts the seal really doesn't verify and that the untampered pair passes. | That test (1 → 4 cases) |
| 2. Probe launch environment | `b2_frozen_support.barrier_env` no longer sets `B2_DRAFT` unless a test forces it. `probe_main` decides drafting from the served registry's `draft_kind` (`fake_probe.served_draft_kind`) and hashes the served registry itself. The `p426_world` `load` wrapper removes `FAKE_REGISTRY_SHA` from the launch environment. | Every world leg: the s4 hook tests, s5 `receipt()`, s7, `add_{pair,argv,census,ledger,a4}`, the fix cases. The s7 test that forces `B2_DRAFT=0` is unchanged. New s0 test: `test_the_two_arms_probe_launch_environments_are_equal_after_canonicalization`. |

**Baseline:**
```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py bench/tests/test_b2_frozen_add_support_check.py
54 passed in 24.25s
../bin/run_stack_tests.sh <17 frozen/add_ files + test_b2_frozen_fix_cases.py> --tb=no -rp
372 failed, 10 passed in 12.19s
```
The 10 passes are the same `[INV]` tests as before.

## 2. Reproduction tests

New files: `test_b2_frozen_fix_cases.py` (27 cases, all [FIX]) and `b2_frozen_fix_support.py`. On the baseline: `27 failed in 0.39s`.

On the first baseline run the two P31 tests passed vacuously, because the baseline refuses `--p426`. I added a precondition that the Python invocation ran, and both now fail.

| Finding | Test |
|---|---|
| R2 | `test_fix_r2_a_frozen_record_whose_seal_does_not_verify_refuses_at_entry` |
| R3 | `test_fix_r3_the_dnf_limit_counts_the_whole_leg_across_languages` (2 Python + 1 Go DNF in one s1 leg) |
| R4 / P20 | `test_fix_r4_a_router_replaced_with_the_same_config_after_load_is_systemic` (same pid and config, new `create_time`) |
| R5 | `test_fix_r5_predictor_mtp_reads_the_served_registry_ops_overlay` |
| §16 refusals, `--rehearsal`, `--inject` | `test_fix_an_argparse_refusal_prints_one_refused_line_naming_the_flag` ×2, `test_fix_inject_without_rehearsal_refuses_naming_inject`, `test_fix_a_rehearsal_leg_is_parsed` |
| `generic_pred_s` | `test_fix_the_generic_prediction_is_recorded_in_chain_json` |
| `p426_invalid` | `test_fix_p426_invalid_is_a_list_of_records` |
| P16 | `test_fix_p16_a_normal_row_whose_termination_has_kill_key_names_is_not_a_kill`, `test_fix_p16_a_failed_line_on_a_normally_completed_item_is_a_problem` |
| P17 | `test_fix_p17_a_dnf_reconciles_against_the_abort_manifest_the_probe_writes` ×2 |
| P19 | `test_fix_p19_an_a4_window_that_differs_from_gate_json_stops_the_leg_before_item_one` |
| P21 / P22 | `test_fix_p21_p22_an_invalidated_done_writes_its_item_record_with_the_ready_files_sha256` (worker replaced before `done`) |
| P23 | `test_fix_p23_a_dnf_records_its_item_record_as_the_path_string` |
| P24 | `test_fix_p24_log_bounds_are_portable_and_finalized_when_the_teardown_raises` |
| P25 / P26 / P27 | `test_fix_p25_…`, `test_fix_p26_…`, `test_fix_p27_…` |
| P29 | `test_fix_p29_a_missing_seam_is_systemic_never_a_skip` |
| P31 | `test_fix_p31_a_worktree_that_turns_dirty_between_invocations_stops_the_next_one`, `test_fix_p31_a_frozen_record_changed_between_invocations_stops_the_next_one` |
| P33 | `test_fix_p33_a_worker_argv_with_extra_leading_tokens_is_systemic` ×2 |
| P34 | `test_fix_p34_pair_problems_takes_two_receipts_and_write_dossier_the_arm_specs` |

**Findings I could not reproduce as a test:**
- **R6:** the report says it was already conformant, so there is no failing case.
- **R7:** a test-infrastructure change (the recorded golden refresh), not product behaviour.
- **P18:** the settle bound shows up in no named record or seam. A chain-level reproduction needs an item that settles between 900 s and the amendment's bound, which needs a chain clock seam the spec doesn't name.
- **P32:** the report says it was already satisfied before the fix, so there is no failing case.

**Will stay red after the fix:** R3 and P23 drive DNF legs, so they will fail on the fixed copy too until the queued flat-layout DNF defect is fixed.

## 3. Whole frozen set on the fixed copy (holds `frozen5`)
```
../bin/run_candidate_fix_tests.sh <s0, add_support_check, s1–s9, all add_ files> --tb=line -rfE
108 failed, 297 passed in 128.70s
```
s1 through s4, `add_a4`, `add_argv`, `add_census` and `add_record` have no failures.

| Failures | Class | Evidence |
|---|---|---|
| s5 seal test (1); add_pair `second_leg…`, `same_credential_keys…` (2) | (c) mine, amended in 2d | `assert []` (no-op tamper); the probe environment carried `B2_DRAFT` / `FAKE_REGISTRY_SHA` |
| s0 `legacy_chain_goldens_hold_on_the_base_commit`, `item_barrier_fake_probe_completes_under_the_baseline_chain…` (2) | (c), by design | These are baseline-only checks: `tg1() missing … 'picks'`, and the baseline argv without `--models` refused (`run_tg1_chain.py:216`). They are not a candidate finding. |
| add_ledger `dnf_is_ledgered…`; s7 `records_destined_for_main…`, `p426_dnf_record…fields`, `transport_dnf…` ×3, `dnf…rebaselines…`, `third_dnf…` (8) | (a), queued | `CHAIN ABORT: DNF refused: … row_arm: python/p1 None != 'oc'` (the flat-layout `arm_row_problems` defect) |
| s7 `a_failed_ready_check_invalidates_before_the_items_go` (1) | **(a), new** | rc 0 where 2 is expected. §3 "Item `ready` barrier: registry sha, lifecycle hash, worktree clean": the hooks check only identities and log bounds. |
| s7 `failed_entry_check…` [head, dirty, identity] (3) | (d) | Now `CHAIN ABORT: before launch (systemic)`, but after the router started. §3's entry row requires them before the router. The fix put them only in the before-invocation checks. |
| s7 `failed_entry_check…` [busy, idle_gap, power] (3); s7 locks ×10 (lines 27, 34, 45, 55, 350, 364, 370, 397); s7 rehearsal smoke shape (1) | (b), s7 not built | rc 0 where refusal is expected; `GateReached()`; the rehearsal behaviour "comes in s8" per the fix report |
| s6 ×3 | (b), s6 not built | `main() got an unexpected keyword argument 'power'`; watch-line count |
| s8 ×21; sequencer ×26 | (b) | `cannot import name 'p426_wave2'` / `'p426_freeze'` |
| s9 ×21; add_scrub ×3 | (b), s9 not built | No `HARVEST.json`; `publish_*` absent; `Scrub(…, emails=)` unknown |

## 4. Review of the fix diff

| Id | File:line (diff) | Severity | Finding |
|---|---|---|---|
| P36 | `p426_hooks.py` 499–512 / 515–521 | Medium | **Ready-barrier checks are incomplete.** At the ready barrier the hooks check identities and log bounds only. §3's ready row also requires the registry sha, the lifecycle hash and a clean worktree. A worktree edited mid-invocation is noticed only before the next invocation, so the frozen s7 test fails. |
| P37 | `chain_core.py` 146–167, 182–193, 241–258 | Medium / (d) | **Entry checks run too late.** HEAD, cleanliness, registry sha and probe identity are checked before every invocation but never at entry. A dirty worktree starts the router and loads the worker before the leg stops; §3 wants a `REFUSED` before the router. |
| P38 | `test_b2_s5_receipt.py` / `test_b2_s1…s5` (30 tests deleted) | Medium | **Coverage dropped beyond the findings.** These deleted tests have no successor in `test_b2_fix_chain.py`: the descendant-worker census, the start-time worker census, the foreign process appearing before an invocation, snapshot drift after load, pre-router snapshots, "a legacy chain runs none of the receipt checks", and the chain-level pair gate (OFF after ON, a credential key, a difference outside the list, the `--pair-receipt` refusals). Some are covered by frozen `add_pair` / `add_census` / `add_argv`; snapshot drift after load and the legacy invariant are covered nowhere. |
| P39 | `p426_hooks.py` 573 | Low | `after_attempt` reads `/metrics` before writing the item record. Unreadable metrics raise `HookInfrastructureError` with no record, contradicting the "every `done` outcome" claim for P21. |
| P40 | `chain_core.py` 294 | Low | Entry refusals go to the run log as `REFUSED:` via `self.log`, not as the §16 stderr line. |
| P41 | `chain_core.py` 46–59 | Low | `p426_settle_bound` swallows a `RecordError` and falls back to 900 s. It is masked today only because the entry refuses a bad record first. |
| P42 | `chain_ops.py` 440–441; `p426_receipt.py` 598 | Low | `interpreter_inventory(pid)` now also takes a path as its positional argument, overloading a §16.2 seam. `ChainOps.worktree_state()` takes no argument, while §16.4's `p426_freeze` seam is `worktree_state(path)`. |
| P43 | `p426_receipt.py` 685–721 | Info, beyond findings | `write_dossier` no longer refuses a passing dossier that carries pair problems; verdict consistency is now the caller's job. It now validates `pair` against the §16.7 labels. |
| P44 | `p426_reconcile.py` 876–877 | Low / (d) | A kill is now any non-empty `termination.killed`, or a non-null `in_flight_at_kill`. If the probe ever records killed cleanup processes on a normally completed item, that item is reconciled as a kill. The 16 fixture rows show no such case, which is too few to rule it out. |
| P45 | `run_tg1_chain.py` 2347 | Info, beyond findings | `pred_default_s` was renamed to `generic_pred_s` in the ChainConfig params, which changes every tg1 config hash. The frozen C221 config-diff test and the legacy differential still pass. |
| P46 | `chain_core.py` 110–123 | Low | The A4 window check reads `<STACK_WORKDIR>/c102a/gate.json` with no freshness check. A stale file from an earlier gate run can only cause a mismatch abort, never a false pass. |

Sound as built:
- Router identity as `(pid, create_time(pid))`, bound when the router starts and compared after load, before each invocation, in the hooks, at incidents and at exit.
- The missing-seam refusal.
- The exact worker argv.
- Structured kill detection.
- The s2 manifest keys.
- Strings as logged.
- The 3-argument A4 equality.
- Portable `log_bounds.json` with finalization in `finally`.
- The DNF limit counted per leg.
- The §16.7 signatures for `pair_problems` / `write_dossier`.
- The `REFUSED:` argparse parser.
- The frozen record read at entry and again before every invocation.

My recommendation: P36 and P37 are the fixes that matter before s5 is called done, ideally in the same final round as the queued flat-layout DNF defect. P38 (the lost coverage) is cheap to restore and worth asking for at the same time.

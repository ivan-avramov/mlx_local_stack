Both clarification items are done. `test_b2_frozen_s0_support.py` now passes, and tg1 Go's own docker failures are typed, so they get regraded like tg2's.

## Item 1: X18, `test_b2_frozen_s0_support.py`

| edit | clause |
|---|---|
| (a) `b2_frozen_support.py` `FROZEN_RUNNERS`: the pin for `benchmark/chains/c147/run_inject.py` goes from `6e139650…` to `3d27a1cc…`, with a comment naming S27 §4.5 / §9. No other pin changed. | §4.5 (the tg1 interrupt run), §9 (identity rotation) |
| (b) `test_b2_frozen_s0_support.py::test_the_abort_manifest_fixture_extends_the_real_probe_stamp`: the expectation now requires the real probe stamp's cleanup keys to equal `ci.CLEANUP_KEYS_2`, with `schema == 2`. It also asserts that this set is exactly the schema-1 keys plus `schema`, `foreign_new`, `foreign_new_count` and `unreadable_count`. Schema 1 still validates: `ci.cleanup_problems(CLEANUP_EXACT) == []`, and the fixture's own cleanup keys are still the schema-1 set. | §3.5 |

- **Pin value:** `3d27a1cc…` is the working tree's `run_inject.py`, meaning candidate 1 plus my X1 change in this round. Candidate 1's own index bytes hash to `384f4aba…`.
- **Choice in (b):** I left the shared abort-manifest fixture and the fake probe on schema 1 and changed only this expectation, because many other tests consume that fixture.
- **Result:** the file passes, 45 passed and 2 skipped. `test_b2_frozen_add_support_check.py` also passes after the support edit, as part of the item 2 run below.

## Item 2: X6 for tg1 Go, `structured_grade.py`

**Change:** `structured_grade.parse_go` now types only docker's own exit statuses, and imports `GraderInfraError`:
- rc 125 (docker could not create or start the container) raises `GraderInfraError(kind="spawn")`.
- rc 126 or 127 (the pinned image's command cannot run) raises `GraderInfraError(kind="image")`.
- A stderr pattern match without one of those statuses still raises a plain `TransportAbort("Docker infrastructure failure: …")`. It aborts as before but is never typed, because the container's stderr carries the agent's test output.

**Red tests** (in `test_s27_impl_r1fix.py`):
- `test_x6_tg1_go_dockers_own_failure_status_is_a_typed_grader_infrastructure_fault[125/126/127]`: failed 3 before the change, passes after.
- `test_x6_tg1_go_test_output_naming_a_docker_fault_still_aborts_but_is_never_typed` (3 cases): passed before and after. It pins that untyped path.

**Existing tests:** unchanged and passing, including the stderr-abort cases in `test_structured_grade.py::test_infrastructure_failure_aborts` and `test_p604_go_package_load.py::test_docker_failures_still_abort_first_P604`.

My previous report's line saying tg1 Go docker faults could not be typed within scope no longer applies.

**Combined run** (23 modules: the X6 tests, `test_structured_grade`, `test_p604_go_package_load`, `test_m62_revision5`, `test_m62_tools`, `test_tg1_runner`, `test_tg1_integration`, `test_c147_grade_reports`, `test_p371_corpus_tg1`, `test_p371_corpus`, `test_p607_p371_grader_pair`, `test_p311_identity`, `test_p311_closure`, `test_p371_closures`, `test_m76_b4b1_fe_grade`, `test_m76_b4b1_impl_corpus`, `test_m76_b4b1_fe_corpus`, `test_m64_arm_closure`, `test_s27_impl_runner`, `test_s27_fe_grader`, `test_b2_frozen_s0_support`, `test_b2_frozen_add_support_check`, `test_tg2_grade`): **947 passed, 102 skipped, 5 failed.** All five are failures already in my previous report:
- `test_m64_arm_closure::test_the_tg1_carrier_and_plugins_the_arm_wraps_are_unedited_by_this_build` is environmental: `GATE_PUSHED_BASE` is unset and this clone's origin isn't the canonical remote. It is also in candidate 1's `final.txt`.
- `test_s27_fe_grader` ×4 are the frozen-test conflicts I escalated (X6 ×3, X3 ×1).
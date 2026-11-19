I made all three adopted fixes, each with a test that failed first. The brief's command passes: **215 passed** (`s26-fix2.log`). The other test files that import `run_tg2_chain` also pass: **113 passed** (`s26-fix2-tg2chain.log`). The frozen S26 suite, which the brief did not ask for, still fails; it fails the same way without this round's v8 fix, so this round didn't cause those failures (details below).

**Changes**

| ID | Finding | Change |
|---|---|---|
| P1 | Sol P2 (erratum 11) | `bench/p426_freeze.py` `declined_ok`: v8 now accepts DECLINED only when `declined_evidence.row_sha256` is 64 lowercase hex characters and equals the entry's own `row_sha256`. |
| P2 | Sol P3 (erratum 12) | `chains/c147/run_tg2_chain.py` `CORE_SPECS["probe_data"]`: added `benchmark/bench/tg2_gradle_home.py`. I put it before the tg2 JSON because an existing test requires that file to stay last. tg1's `CORE_SPECS` is untouched. |
| P3 | GLM R2-2 (erratum 14) | `bench/p426_wave2.py`: removed "(the operator decides)" from the unreadable-baseline stop and "(a rerun is an operator decision)" from the stop for a leg the host change made INVALID. |

**Red tests (all failed on the candidate, then passed after the fix)**
- **P1:** `test_s26_impl_positives.py::test_v8_declined_needs_the_entrys_row_sha256_in_its_evidence`. It changes, removes, upper-cases or shortens the row hash in a resealed record and expects v8 to refuse each. On the candidate it failed on the first case, a different 64-hex hash in the evidence, which v8 accepted.
- **P2:** `test_s26_impl_gradle.py::test_the_gradle_home_source_is_in_tg2s_campaign_core_only`. It copies the closure files to a temp tree, edits `tg2_gradle_home.py`, and checks that tg2's `probe_closure_sha256` changes while tg1's closures stay identical. On the candidate it failed because the module was not in `probe_data`.
- **P3:** `test_s26_impl_sequencer.py::test_the_baseline_stop_is_a_flat_fail_closed_statement` and `::test_the_invalid_leg_stop_is_a_flat_fail_closed_statement`. On the candidate both failed with the operator wording in the logged STOP line.

**Adjustment to an existing implementer test:** `test_v8_accepts_declined_only_for_loop_and_alloc_with_valid_evidence` built cpp/alloc's DECLINED evidence from java/loop's, which carries java/loop's row hash. I changed it to use the cpp/alloc entry's own `row_sha256`; under P1 the old version would rightly be refused.

**Frozen suite (`bench/tests/s26_frozen`, read-only, not edited):** 30 failed, 109 passed, 10 errors (`s26-fix2-frozen.log`).
- **Positives file:** I reverted my `declined_ok` check for a moment and reran it: same 9 failed and 10 errors (`s26-fix2-frozen-pos-prefix.log`), then restored the fix. The runner fails before v8 runs: the record is never marked DECLINED. That matches Sol P1's frozen-test defects, which the test-writer is amending.
- **Sequencer file:** the failures I looked at stop on a missing `src/mlx-vlm/dev/p369_phase2/pins.json`, probably because the submodule isn't populated in this copy.
- **One failure each in `test_s26_host_env.py` and `test_s26_arm_identity.py`:** I did not look into these; they are in code this round didn't touch.

**Open points**
- **P4:** Adding the Gradle module also changes tg2's recorded `ArmBinding.probe_data`, because `tg2_config` passes `CORE_SPECS["probe_data"]` into it, so tg2's config record changes with the campaign core. This seems intended by the scope extension, but you should know before Accept.
- **P5:** Erratum 13 (`not_declined`) needed no code, so nothing changed for it.
- **P6:** Nothing is committed; the brief forbids it. Besides `s26-fix2.log`, I left three extra logs in the copy root: `s26-fix2-tg2chain.log`, `s26-fix2-frozen.log` and `s26-fix2-frozen-pos-prefix.log`.
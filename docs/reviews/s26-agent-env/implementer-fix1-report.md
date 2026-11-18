Phase A is finished: every adopted row and erratum items 1–6 and 8 are implemented. No test has been run yet. The only command I ran was `py_compile` on the nine changed or new Python files, and it printed `OK`.

**Files changed**
- `benchmark/bench/p426_freeze.py`: only `not_observed*` verdicts can be declined now, so `FAIL:no_shell_part` and `competing_trigger:*` stay failures. v8 also requires `kills == 0` and `probe_rc == 0` in `declined_evidence`. Serves Sol P1, Sol P17, erratum 1.
- `benchmark/bench/p426_wave2.py`:
  - DECLINED now needs all of: a `not_observed*` verdict, probe rc 0, a row whose `row_sha256` checks out, no recorded kill (`mem_kills` and `termination.killed` both present and empty), the artifacts verifying against `evidence_sha256`, and no marker in any tool call. Serves Sol P1 and P17, erratum 1.
  - A nonzero probe exit becomes `FAIL:probe_rc:<n>`. A PASS whose row file exists but doesn't match `row_sha256` becomes `FAIL:row_sha256`. Serves Sol P17.
  - `BoxSeqOps.inject_verify` returns the retained attempt's own verdict string instead of `FAIL (inject_verify rc N)`. Serves Sol P19 / GLM F1, erratum 3.
  - `BoxSeqOps.host_env()` calls `fingerprint_for_run()` with no argument. Serves Sol P20, erratum 4.
  - Problem lines keep the existing `<lang> <kind>: <verdict>` format; the reason a run was not declined goes into a new per-entry field, `not_declined`.
- `benchmark/m62/inject_verify.py`: new `never_executed(state)`. The alloc rule now counts only shell calls that actually ran and carry `bytearray(`; a call with `status == "error"` and `providerCall.executed is False` is excluded. Every other rule is unchanged. Serves the scope extension, erratum 2.
- `benchmark/bench/arm_opencode.py`: the bytes of `tg2_gradle_home.py` now enter tg2's `probe_code_sha256`, via new `TG2_GRADLE_HOME_SOURCE` and a new `identity_data` property. I did not add it to `TG2_GENERATION_DATA`, because `test_m76_b4b1_impl_probe.py:64` asserts that tuple exactly. tg1's data and closure are unchanged. Serves Sol P18, erratum 5.
- `benchmark/bench/tg2_gradle_home.py`: `PREFILL.json` is written without a self-seal, and `check` no longer requires one. Serves Sol P21, erratum 6.
- My own tests (`test_s26_impl_positives.py`, `test_s26_impl_gradle.py`, `test_s26_impl_sequencer.py`) are updated to the erratum, with new cases for each change.
- New `test_s26_impl_inject_verify.py` uses the recorded java alloc row shape. It should give PASS, where the baseline gives `FAIL:no_shell_part` (the red test). It also covers a mismatched kill id → `FAIL:tool_call_id` and two executed marker calls → `FAIL:no_shell_part`. Serves erratum 2.

**Judgement calls and deviations**
1. **"The row records no kill"**: I count `termination.killed` as well as `mem_kills`, and treat either field missing as a kill. A real row that ends normally has `killed == []`. A client kill with a `not_observed:kill` verdict means something like a runner cancel or exit hang, not a decline, so this is the fail-closed reading.
2. **PASS row check is lenient**: it applies only when the row file exists, and an unrecorded probe rc doesn't fail a PASS. Without this, the existing `test_m76_b4b1_impl_wave2` PASS fakes (no row on disk, no `rc`) would fail against acceptance 2. DECLINED requires both strictly.
3. **The tg2 chain's `CORE_SPECS`** (`run_tg2_chain.py`, out of scope) does not include `tg2_gradle_home.py`. The arm identity binds it; the campaign core closure does not.
4. **One assumption in my new test**: the shape note doesn't record the retry's `state.metadata`. I assumed `exit: 137` so the existing killed-shape rule accepts it.

**Frozen tests I judge unsupported by the spec** (all in `s26_frozen/test_s26_positives.py`). Expect these to fail in Phase B:
- **`FAIL:no_shell_part` declined** (erratum 1 says it stays a failure):
  - MATRIX case `alloc-FAIL:no_shell_part-bare`, which expects DECLINED.
  - `test_fix_declined_runs_pass_the_record_in_every_language`, which expects cpp alloc `FAIL:no_shell_part` → DECLINED.
  - `test_new_v8_accepts_alloc_no_shell_part_as_the_declined_verdict`.
- **DECLINED on a fixture row that records a kill**: every other DECLINED expectation uses a re-labelled stall row whose `termination.killed` holds a client kill. Under point 1 that row "records a kill", so it is not declined. Affected:
  - The MATRIX DECLINED rows.
  - `test_inv_one_abort_then_a_decline_on_the_retry_is_a_decline`.
  - Every test using the `declined_record` fixture (its setup assert fails).
  - Both `test_fix_real_verify_*` hybrid tests.
  - If you rule that a kill means `mem_kills` only, change `recorded_kills` in `p426_wave2.py`, and these pass except the `no_shell_part` ones above.

I didn't satisfy any of these, and no adopted finding was left undone. The scope also lists GLM F5, but those are the test-writer's additions, not implementer work.
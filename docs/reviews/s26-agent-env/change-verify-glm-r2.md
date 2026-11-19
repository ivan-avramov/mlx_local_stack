## Round 2 of 3 — change `verify` (four-eyes strict)

### Disposition of every round-1 finding marked adopted in `change-ledger-r1.md`

| Finding | Status | Why |
|---|---|---|
| **Sol P1** `FAIL:no_shell_part` declinable (blocker, full) | **resolved** | `bench/p426_freeze.declinable_verify_verdict` admits only `not_observed`/`not_observed:*`; `decline_evidence` (p426_wave2.py:241) requires a declinable verdict, probe rc 0, a verified `row_sha256`, no recorded kill, verifying artifacts, and no marker tool call. `FAIL:no_shell_part`, `competing_trigger:*`, every other `FAIL:*` stay failures. `declined_ok` (p426_freeze.py:84) checks the same set for v8. Traced and covered by `test_s26_impl_positives.test_alloc_no_shell_part_is_never_declined` and the frozen MATRIX. |
| **(from Sol P1) inject_verify counts a tool-bound-rejected call** (major, scope extension) | **resolved** | `m62/inject_verify.never_executed` (inject_verify.py:142) excludes `status=="error"` + `providerCall.executed is False`; the alloc rule filters with `not never_executed(c[4])` (inject_verify.py:261). Red test `test_s26_inject_verify.test_fix_a_rejected_first_call_then_an_executed_retry_linked_to_the_kill_passes` passes; mismatched/extra executed calls → `FAIL:tool_call_id` / `FAIL:no_shell_part`. |
| **Sol P17** nonzero probe exit → DECLINED (major) | **resolved** (stricter, declared) | `positive_entry` sets `FAIL:probe_rc:<n>` for any nonzero rc on PASS *or* DECLINED paths (p426_wave2.py:328); `decline_evidence` requires `probe_rc == 0`. v1.1c erratum 10 adopts the stricter PASS behaviour; the candidate matches. |
| **Sol P18 / impl P1** `tg2_gradle_home` outside tg2 identity (major) | **resolved** | `OpencodeArm.identity_data` (arm_opencode.py:282) appends `TG2_GRADLE_HOME_SOURCE` only when `self.tg2`; `probe_code_sha256` uses `identity_data`. tg1's `identity_data` is `tuple(generation_data)` == `GENERATION_DATA`, so tg1's hash is byte-unchanged (confirmed: `test_m76_b4b1_impl_probe.py:66` and the B4b-1 golden pass). The module is imported by name (`importlib.import_module` in `_tg2_gradle_home`), so it never enters the shared tg1/oc static closure. | <!-- allow-shorthand -->
| **Sol P19 / GLM F1** `inject_verify` returns `FAIL (rc N)` (blocker) | **resolved** | `BoxSeqOps.inject_verify` returns `inject_verify_result(...)["verdict"]` (p426_wave2.py:1742); `parse_inject_verify` extracts the retained attempt's verdict string and the `RESULT` line. Covered by `test_the_box_inject_verify_returns_the_retained_attempts_verdict`. |
| **Sol P20** `host_env()` passes `workdir=` (minor) | **resolved** | `BoxSeqOps.host_env` calls `host_env.fingerprint_for_run()` with no argument (p426_wave2.py:1599). Covered by `test_the_box_host_env_calls_fingerprint_for_run_with_no_argument`. |
| **Sol P21** PREFILL self-seal beyond spec (minor) | **resolved** | `tg2_gradle_home._write_exclusive_json` writes without a self-seal; `check_problems` does not require one (tg2_gradle_home.py:190, :214). `prefill_sha256` in the identity binds the receipt. |
| **Sol P22** tg1 "byte-identical" wording (minor, spec) | **resolved** | tg1 env (`build_env` returns the core hermetic env, no `GRADLE_USER_HOME`), argv, and `scaffold_policy_sha256` are unchanged; `gradle_user_home` is omitted from `GenerationPolicy.as_dict`/hash when None (run_config.py:101, :125). `test_inv_the_tg1_policy_is_untouched_by_the_gradle_home` and `test_inv_tg1_env_is_exactly_the_core_hermetic_env` pass. |
| **GLM F1** (= Sol P19) | **resolved** | as above |
| **GLM F3 / impl P6** a host-changed R2 stops (minor, declined → erratum 8) | **resolved via erratum 8** | `after_leg` raises `Stop(1)` for any INVALID leg whose reason starts with `HOST_ENV_REASON`, even where INVALID is expected (p426_wave2.py:1311). `test_a_host_change_stops_even_a_leg_whose_invalid_state_is_expected` and `test_fix_the_kv_lever_sequencer_guards_the_host_too` (resume path) cover it. |
| **GLM F5** test gaps (minor) | **resolved** | the frozen delivery adds `test_fix_the_kv_lever_sequencer_guards_the_host_too`, `test_inv_the_bootstrap_script_is_valid_bash`, `test_fix_an_exception_message_never_carries_the_absolute_home_path`, and the B4b-1 tg1 golden runs in phase B (per the test-writer's report). |

The declined items (GLM F2 `main` finally republish; the second GLM F3 reading) were not adopted and need no work. Sol P2–P16 were design-only and out of scope for the fix round.

### Anything else the diff breaks or leaves failing

The three frozen-test failures the test-writer reports are test defects, not candidate defects, and I agree with each judgment:

- **T1** (`test_new_the_real_tg2_print_identity_carries_the_gradle_policy`): the test calls `prefilled.check()` (which prints `OK: …`) between two `print_identity` reads without draining `capsys`, so the third JSON parse sees the check's line first. Test bug.
- **T2** (`test_new_an_unreadable_tool_binary_records_error_and_never_raises`): mode `000` strips the execute bit, so `shutil.which` returns `None` → `"absent"` (which is also what the agent would see). The candidate's behaviour is defensible and an `0111` unreadable binary does record `error: PermissionError`. Test bug.
- **T3** (`test_fix_the_kv_lever_sequencer_guards_the_host_too`): the test hand-writes an *unsealed* baseline. v1.1c erratum 10 makes the baseline sealed; the candidate's `host_baseline` rejects it with `Stop(1)` "unreadable or not a sealed baseline", so the test's expected pre-launch refusal message never appears. Test bug (amend to write a sealed baseline via `ph.seal`/`ph.write_exclusive`).

The full suite is otherwise green (15194 passed), including `test_m76_b4b1_impl_wave2` (so the lenient PASS-row check in judgement call #2 preserves the existing PASS fakes) and the B4b-1 tg1 golden.

### Round-2 findings

**R2-1 (minor, confirmed).** `p426_wave2.positive_entry` writes a per-entry `not_declined` diagnostic field (p426_wave2.py:340) that is not in the spec's record schema (§4 lists only `verdict` and, when DECLINED, `declined_evidence`) and is not among the documented extensions in erratum v1.1a item 7. It is harmless (PII-scrubbed via `he.portable`, never affects the verdict or v8), but it is an undocumented schema extension.
- *Scenario:* a consumer that round-trips the sealed positives record against a fixed schema rejects the record on the unknown key, or a future v8 check that enumerates inject-entry keys trips on it.
- *Proposed change:* add `not_declined` to the documented extensions in erratum v1.1a item 7 (spec edit), or drop the field and keep the reason only in the problem line. (scope request — no severity unless the operator wants the schema pinned.)

**R2-2 (minor, confirmed).** `Sequencer.host_baseline`'s Stop message ends with `(the operator decides)` (p426_wave2.py:837). The spec (§2 + erratum 10) specifies the behaviour (unreadable / unsealed baseline → `Stop(1)`) but not that parenthetical, and every other Stop in the guard is worded as a flat fail-closed statement. The phrase implies discretion where the spec makes it automatic.
- *Scenario:* an operator reading the log reads "(the operator decides)" as "await a ruling" rather than "the run already stopped rc 1".
- *Proposed change:* drop the parenthetical, e.g. `STOP: host_env.json (the run's host-environment baseline) is unreadable or its seal does not verify`.

**R2-3 (scope request, not a defect).** The spec body (§3 / erratum v1.1a item 5) says tg1's closure-derived `probe_code_sha256` "rotates (C178)", but the implementation imports `tg2_gradle_home` by name inside a function, so it never enters tg1's static closure and tg1's `probe_code_sha256` is byte-unchanged (the B4b-1 tg1 golden passes unmodified). The implementation is stricter/better than the spec text; the spec wording should be corrected to "unchanged" so a future reader does not re-introduce a static import to "match" it. No code change. <!-- allow-shorthand -->

**R2-4 (hazard note, not a defect in this candidate).** `host_env_final` is only on the two normal exits of `run()` (DONE and `--through`); a mid-run `Stop` from a host-changed leg bypasses it, so `host_env_after_last_leg` is not set on that path. This matches the spec (finalization is only the two exits; the leg-level diff is already in `leg.json`/`sequence.json`), and erratum 8's "`main`'s existing `finally` still publishes the run files" covers publication. Recorded here so it is not later reported as a gap.

No blocker or major finding against the candidate. The candidate resolves every adopted round-1 finding, the three frozen-test failures are test defects (T3 specifically follows v1.1c erratum 10, which the candidate correctly implements), and the remaining items are minor wording / documentation nits and one spec-vs-code wording correction.

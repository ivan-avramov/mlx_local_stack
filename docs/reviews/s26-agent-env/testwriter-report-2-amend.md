I amended the tests against spec v1.1b and added the new ones. Nothing has been run. The only check was `py_compile`, which passed on every file in `s26_frozen/`.

## Amended tests (`test_s26_positives.py`, `s26_support.py`)
- **A1. MATRIX `alloc-FAIL:no_shell_part-bare`.** Now expects `FAIL:no_shell_part`, with or without a marker in the events (erratum 1). I added two `competing_trigger:turn_cap` rows (loop and alloc) to the matrix. Class [FIX].
- **A2. `test_fix_declined_runs_pass_the_record_in_every_language`.** The cpp alloc case now uses `not_observed:kill`. Class [FIX].
- **A3. `test_new_v8_accepts_alloc_no_shell_part_…` is replaced** by `test_fix_v8_refuses_declined_with_fail_no_shell_part`, parametrized over alloc and loop. `FAIL:no_shell_part` is also added to the refused-verdicts parametrization. Class [FIX].
- **A4. DECLINED fixtures rebuilt (erratum 9).**
  - `write_inject_run` takes a `shape` argument. The default for loop and alloc is `completed`: row `stop_reason` "completed", gate stop `None`, `mem_kills == []` and `termination.killed == []`. Stall keeps the recorded row.
  - This fixes the MATRIX DECLINED rows, the retry-decline test, `declined_record` and its users, and both `test_fix_real_verify_*` tests, with no per-test edits.

## New tests
- **N1. `test_fix_a_not_observed_row_with_any_kill_is_not_a_decline`.** Four cases: loop and alloc, each with a client kill and with a memory kill. The verdict stays `not_observed:kill` and the record FAILS. Class [FIX].
- **N2. `test_fix_a_row_that_records_no_kill_field_at_all_…`.** A missing `mem_kills` or `termination.killed` is not a decline, because the spec requires both to be "present and empty". Class [FIX].
- **N3. Hybrid test.** The real `inject_verify` says `not_observed` for a loop row that records a client kill; it is not declined, while the alloc rows still are. Class [FIX].
- **N4. `test_fix_a_nonzero_probe_exit_that_left_a_row_is_not_a_decline`.** Covers loop and alloc. Class [FIX].
- **N5. `test_fix_a_row_sha_that_does_not_verify_is_not_a_decline`.** Covers loop and alloc. Class [FIX].
- **N6. `test_fix_an_exception_message_never_carries_the_absolute_home_path`.** The exception message holds the real home path, and the sealed record must not. Class [FIX], per the AGENTS.md rule on home paths.
- **N7. New file `test_s26_inject_verify.py` (erratum 2).** Rows are real-shaped and judged by the real `iv.main`.

  | Case | Expected | Class |
  |---|---|---|
  | rejected call, then an executed retry linked to the kill | `PASS` | [FIX] |
  | kill linked to another part id | `FAIL:tool_call_id` | [FIX] |
  | kill linked to the rejected call | `FAIL:tool_call_id` | [FIX] |
  | two executed marker calls | `FAIL:no_shell_part` | [FIX] |
  | only a rejected call | `FAIL:no_shell_part` | [FIX] |
  | a single executed call with no rejection | `PASS` | [INV] |
  | an `error` part that did execute is counted, not excluded | `FAIL:no_shell_part` for two of them | [INV] |
  | a `completed` part is counted | reaches `FAIL:killed_part_shape` | [INV] |

- **N8. kv-lever sequencer test (`test_s26_sequencer.py`).** A resumed kv run on a changed host stops with rc 1, launches nothing, and logs the pre-launch message naming `tg1-m76-n16-pilot`. Class [FIX].
- **N9. New file `test_s26_bootstrap.py`.** `bash -n` on `scripts/bootstrap_machine.sh` ([INV]). A text check for `brew link --force openjdk@21` and `bench.tg2_gradle_home prefill`, and for the rust / openjdk@21 / cmake install ([NEW]). The script itself is never executed.

## Removed
None. A1–A3 were rewritten in place because their old expectations contradicted the spec. The docstring of the sequencer test and a weak assertion in the bootstrap test were tidied.

## Still ambiguous
- **P1. N8 covers only the entry comparison.** The kv first-run baseline and post-leg INVALID paths would need frozen kv records and kv chain fakes. I did not find these in the test base, and wiring them myself was not safe without running anything. The tg2 corpus run path is likewise untested.
- **P2. Decline-shape fixtures.** I set the row's `stop_reason` to "completed" and `gate.stop_reason` to `None`, because inject_verify returns `competing_trigger:completed` for a loop row whose gate says "completed". The spec's "`stop_reason: completed`" is read as the row field.
- **P3. Case N2 (absent kill fields).** It follows the "present and empty" wording of erratum 9; an implementation treating an absent key as empty would fail it.
- **P4. Hybrid memory-kill row.** I did not build one. The real `inject_verify` would answer `FAIL:no_shell_part` for it, not `not_observed`, so memory-kill rows are covered only at the fake-ops level.
- **P5. N6 assertion.** It only requires that the home path be absent. Whether the implementation redacts it or drops the message is not specified.
- **P6. Test count.** `test_s26_positives.py` now has about 70 tests, up from 55.
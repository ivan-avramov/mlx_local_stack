Verdict: merge. I found nothing in the candidate that needs a fix, and the three frozen-test failures are defects in my tests (see the table). Nothing was fixed or edited.

## Results

- **Frozen tests, candidate:** 173 passed, 3 failed (`s26-candidate-frozen.log`).
- **Full stack suite, candidate:** `3 failed, 15194 passed, 9 skipped, 1 xfailed, 3 warnings in 6429.63s (1:47:09)` (`s26-candidate-suite.log`). The failing test ids, verbatim, are the same three frozen tests listed below:
  - `bench/tests/s26_frozen/test_s26_arm_identity.py::test_new_the_real_tg2_print_identity_carries_the_gradle_policy`
  - `bench/tests/s26_frozen/test_s26_host_env.py::test_new_an_unreadable_tool_binary_records_error_and_never_raises`
  - `bench/tests/s26_frozen/test_s26_sequencer.py::test_fix_the_kv_lever_sequencer_guards_the_host_too`
- **Acceptance 2** therefore holds: nothing else in the suite fails, including the B4b-1 tg1 golden.
- I did not run the baseline step, as instructed. The baseline column below is my earlier run, where 21 sequencer tests failed on a missing submodule file.

## Frozen tests: baseline vs candidate

| file | tests | classes | baseline (pass/fail/error) | candidate |
|---|---|---|---|---|
| `test_s26_host_env.py` | 33 | [NEW]/[FIX]/[INV] | 0 / 33 / 0 (no module) | 32 pass, 1 fail |
| `test_s26_sequencer.py` | 23 | [NEW]/[FIX]/[INV] | 0 / 23 / 0 (21 of the 23 failed on the missing submodule, so they were not a true baseline) | 22 pass, 1 fail |
| `test_s26_positives.py` | 67 | [FIX]/[NEW]/[INV] | 33 / 21 / 13 | all pass |
| `test_s26_gradle_home.py` | 29 | [NEW]/[FIX]/[INV] | 1 / 13 / 15 | all pass |
| `test_s26_arm_identity.py` | 14 | [NEW]/[FIX]/[INV] | 1 / 4 / 9 | 13 pass, 1 fail |
| `test_s26_inject_verify.py` | 8 | [FIX]/[INV] | 4 / 4 / 0 | all pass |
| `test_s26_bootstrap.py` | 2 | [INV]/[NEW] | 1 / 1 / 0 | all pass |

The `[FIX]` tests that already passed on the baseline are vacuous there and only discriminate now. They passed on the candidate too.

The three candidate failures:

- **T1. `test_new_the_real_tg2_print_identity_carries_the_gradle_policy`: my test bug.**
  - The test calls `prefilled.check()` before its third `print_identity`.
  - `check` prints `OK: tg2-gradle-home/ verifies against PREFILL.json`.
  - My `capsys` was not drained, so the JSON parse fails (`s26_frozen/test_s26_arm_identity.py:186`).
  - The first two identity reads passed, so the candidate is not implicated.
- **T2. `test_new_an_unreadable_tool_binary_records_error_and_never_raises`: over-strict test.**
  - The test uses mode `000`. `shutil.which` (`host_env.py:60`) needs the execute bit, so the tool is `"absent"`, which is also what the agent would see.
  - An executable file that cannot be read (mode `0111`) does reach the hash and records `error: PermissionError`.
  - The candidate's behaviour is defensible and still detects the change when permissions flip back.
- **T3. `test_fix_the_kv_lever_sequencer_guards_the_host_too`: ambiguity between spec and candidate.**
  - My hand-written baseline file has no `sha256`. The candidate reads it back only if it is sealed (`p426_wave2.py:826`, `ph.sealed_ok`) and stops with "unreadable or not a sealed baseline".
  - Spec v1.1b says the baseline is `{kind, fingerprint, created}`, exclusive-created, and never says sealed or unsealed.
  - Sealed is stricter and good, but it is a deviation the implementer did not list.
  - The kv path itself is therefore still unverified by a frozen test.

## Deviations from the spec

- **D1. Sealed baseline.** Described under T3 above.
- **D2. Nonzero probe exit.** A nonzero probe exit makes even a PASS verdict `FAIL:probe_rc:<n>` (`p426_wave2.py:320`). The spec requires rc 0 only for DECLINED, so this is stricter.
- **D3. PASS row check.** A PASS entry is checked against its row hash only if the row file exists. This is lenient and is declared by the implementer.
- **D4. Fingerprint extras.** The fingerprint adds a `path` section and writes the real home as `~`, which is declared as P4.
- **D5. Positives Refusals.** A Refusal inside the positives, such as a listener already on :8000, now seals a FAIL record instead of returning rc 2. This is declared as P8.

## Findings

- **F1. tg1 closure rotates (declared, medium).** `probe_code_sha256` for tg1 changes. Do not merge into the arm worktrees while the current tg1 Wave 2 is running, because its records pin the old value.
- **F2. Gradle package not in the tg2 chain closure (low).** `tg2_gradle_home.py` is bound into tg2's `probe_code_sha256` through `identity_data` (`arm_opencode.py:282`). It is not in the chain's `CORE_SPECS`, which is out of scope. <!-- allow-shorthand -->
- **F3. Baseline for an already-running out-base (low).** A resumed run of an out-base that predates the guard silently records its baseline at that moment (`p426_wave2.py:855`). It is logged, but nothing says the host was not checked earlier. <!-- allow-shorthand -->
- **F4. Per-item `check_problems()` (low).** `build_env` runs it for every tg2 item (`arm_opencode.py:464`). The directory walk should be cheap, but its cost on the real prefilled home is unmeasured. <!-- allow-shorthand -->
- **F5. Size-only manifest check (declared as P11).** If Gradle rewrites any recorded file under `wrapper/dists/`, items would be wrongly refused. This stays unverified until the first real prefill (acceptance 3, which needs the real box).
- **F6. Gradle-home identity when unprefilled (low).** `identity_policy()` records null hashes if the folder is missing, so print-identity does not refuse. `build_env` does refuse. <!-- allow-shorthand -->

## Verdict

**Merge.** The candidate meets every behaviour the frozen tests encode. Specifically, the host guard works on both the tg1 path (leg INVALID, pre-launch and end checks, exception logging) and the positives path, the decline rule matches erratum 1 and 9, the inject_verify alloc rule matches erratum 2, and tg1's env and policy hash are unchanged.

Before or at merge:
1. Amend T1 and T2 in my tests: drain `capsys` after `check()`, and use mode `0111` for the unreadable-binary case.
2. Operator ruling needed on T3 and D1: keep the sealed baseline and amend the spec and my test, or accept an unsealed one.
3. Do not apply it to the arm worktrees until the running tg1 Wave 2 ends (F1).
4. After merge, run acceptance 3 on the real box: `prefill` rc 0, `check` rc 0, and one tg2 positives run under the new rule.
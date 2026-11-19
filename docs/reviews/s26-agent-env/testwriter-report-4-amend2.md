All 184 frozen tests pass on the candidate (`184 passed in 344.21s`, `s26-candidate-frozen-2.log`). No failures or errors remain.

## Amended
- **T1. `test_new_the_real_tg2_print_identity_carries_the_gradle_policy` (arm_identity), [NEW].**
  - It now calls `capsys.readouterr()` right after `prefilled.check()`.
  - `check` prints an `OK:` line that was corrupting the next JSON read, so this was a defect in my test.
- **T2. `test_new_an_unreadable_tool_binary_records_error_and_never_raises` (host_env), [NEW].**
  - The tool file is now mode `0o111` instead of `0`.
  - A mode-0 file has no execute bit, so it is never on the agent PATH and correctly reads as `absent`.
  - Mode `0o111` is executable but unreadable, so the hash fails and `error: PermissionError` is recorded, which is what the test is meant to check.
- **T3. `test_fix_the_kv_lever_sequencer_guards_the_host_too` (sequencer), [FIX].**
  - It now writes a sealed baseline through `ph.write_exclusive`, as the sequencer's records are sealed (erratum v1.1c 10).
  - The kv comparison therefore really runs: rc 1, no launch, and the exact pre-launch message naming `tg1-m76-n16-pilot`.
  - The setup moved into shared helpers `sealed_baseline` and `_kv_resume`.

## Added
- **`test_new_an_unsealed_or_tampered_baseline_stops_with_rc_1` (sequencer), [NEW].**
  - It covers 4 damage kinds, each with the host both unchanged and changed, for 8 cases in total.
  - The damage kinds are: unsealed, tampered `created`, tampered fingerprint, and unreadable (garbage).
  - Each case stops with rc 1 before any launch, logs `host_env.json`, and does not report a host difference.
  - It checks that a baseline whose seal fails stops the run even when it was edited to equal the live host, and that it does so with the host unchanged too.

The only candidate-side behaviour added by erratum v1.1c, the nonzero-probe-exit rule, was already covered by my earlier tests and passes.

The frozen kv test exercises only the resume comparison. The kv first-run baseline write and the post-leg INVALID path are still not covered by any frozen test, because they need kv chain fakes that the frozen test base lacks.
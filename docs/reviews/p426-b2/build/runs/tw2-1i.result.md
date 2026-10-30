Delivery 1i is done: the three fixture defects are fixed and the tests are aligned with the §16.7 tail. On the baseline the support checks pass and nothing else changed. I didn't run the candidates, as you asked.

**Baseline results**
```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py bench/tests/test_b2_frozen_add_support_check.py
53 passed in 17.45s
../bin/run_stack_tests.sh <the 17 frozen and add_ files> --tb=line -rp
342 failed, 10 passed in 11.61s
```
- The 10 passes are the same `[INV]` tests as before.
- No failure ends inside a support module, and there is no fixture-side `NameError`, `KeyError` or `FileExistsError`.
- In the touched files, the failures are the expected baseline causes: `ImportError` (no `p426_receipt`) and refusal assertions (no `--p426`).
- The new missing-seam test gets rc 2 on the baseline (the baseline rejects `--p426`), so it fails only at the step that requires a line naming the seam.

## The three fixture defects

| Defect | Change (`b2_frozen_support.py`) | Tests touched |
|---|---|---|
| Snapshot shape | New `pinned_snapshots(arm)` returns the fork's `pins.json` entries for the model (`{hf_path, revision, files}`), drafter for ON only. `arm_receipt_doc` and the world's `snapshot_hashes` both use it. | Every test using `arm_receipt_doc` (the s5 pair gate and dossier, the s8 R1 tests, add_support `write_leg`) and every world leg |
| Re-sealing in s5 | `_mutate` now re-seals with `S.self_hashed`. Every in-place edit goes through it. New `problems_naming(off, on, name)` first checks both seals verify, then requires a problem naming the field (dotted receipt path) or key under test. | s5: `volatile_keys_never_count_as_a_difference` ×7, `a_problem_names_the_differing_process_and_field` (also: the value is never echoed), `test_fix_any_other_difference_between_the_arms_refuses` ×8 (each names its field; the loaded-images and target-snapshot values are now valid-shaped), `an_interpreter_inventory_difference_refuses`, `an_env_difference_outside_the_closed_list_refuses`, `a_credential_key_missing_from_one_process_of_one_leg…` |
| `mlx.metallib` | New `LOADED_IMAGES(wt)` lists `libmlx.dylib` and `mlx.metallib`. Used by the world's `loaded_images` and by `arm_receipt_doc`. | Every world leg. Also add_pair `loaded_library_difference…`, which now changes only libmlx's hash and keeps both libraries. |

The 10 former false passes in s5 can no longer pass through a broken seal. The new seal test keeps the seal rule observable separately.

## Aligned with the rulings
- **A missing seam is systemic.** New add_pair `test_new_a_missing_check_seam_is_systemic_never_a_skip`, run once per seam: `proc_argv`, `proc_environ`, `interpreter_inventory`, `loaded_images`, `snapshot_hashes`, `expected_worker_argv`, `busy_procs`, `descendants`, `create_time`. It removes the seam from the instance and class, then requires rc 2, no item started, and a line naming the seam.
- **The worker argv is exact.** add_argv changes:
  - `…three_pairs_appended_passes_position_free` is replaced by `test_new_an_on_worker_equal_to_the_argv_mlx_serve_builds_passes`.
  - New `test_fix_an_on_worker_with_the_three_pairs_at_another_position_is_systemic`. mlx-serve inserts the pairs mid-argv (checked), so OFF plus pairs appended differs.
  - New `test_fix_a_worker_argv_with_extra_leading_tokens_is_systemic`, with `arch` and `env` prefixes.
  - The module docstring is updated.
- **Identities use `create_time(pid)`.** The world already provides it; it is one of the missing-seam cases.
- **Portable `log_bounds.json` paths.** Already in my s4 fixture (1h); unchanged.

## Aligned with the earlier "after delivery 1g" rulings in §16.7
- **Portable record paths.** New `S.portable()` and `WT_PORTABLE = "$STACK_WORKDIR/WT"`. `v8_base` and `rehearsal_manifest` now default to portable worktrees, and the rehearsal `out_root` goes through `portable()`. The world's v8 uses `portable(wt)`. s8 `test_new_freeze_rehearsal_writes_a_self_hashed_rehearsal_manifest_once` now sets `STACK_WORKDIR` and expects `$STACK_WORKDIR/stack-p426-{off,on}` and the portable `out_root`.
- **`ops.build_inputs()`.** Added to s8's `FreezeOps`, so the v8 tests (wrong kind, gitlinks, the three R1 tests) can't refuse on that seam being absent.
- **Dotted `field`.** The s5 `DIFFERENCES` fixture uses `argv.worker` and `snapshots.drafter`, with the pinned drafter revision.
- **`publish_*` return shape.** New s9 `assert_published` requires `{published: [{source, destination, sha256}], harvest_sha256}`, one entry per source with the file's sha256. Used by `publish_dossier…idempotent` and `publish_run_files…wave2_run`.

## New tests
- s5 `test_new_a_receipt_whose_seal_does_not_verify_is_a_problem`
- add_pair `test_new_a_missing_check_seam_is_systemic_never_a_skip` (9 cases)
- add_argv: the 3 tests listed above (4 cases)
- s0 `test_the_records_write_portable_path_fields`
- s0 `test_the_receipt_fixture_pair_differs_only_on_the_closed_list…` gains checks: seals, both libraries, pins-shaped snapshots, and `--draft-model` equal to the drafter's `hf_path`.

## One gap left in the spec
The ruling says the receipt's probe environment is the chain's probe launch environment, but §16.2 still gives `arm_receipt(ops, *, worktree, out_root, pids)` with no parameter for it. My s5 unit tests therefore still pass a probe pid and read its environment from `proc_environ`. I left them, because changing them would mean inventing a parameter name. §16.2 should name how that environment reaches `arm_receipt`.

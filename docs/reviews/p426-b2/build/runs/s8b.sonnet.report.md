All the P59–P63 items and the §16.8 seams and semantics are fixed. The required check run passed: 512 passed in 110.30s. I did not run the full suite and did not commit.

`docs/specs/p426-b2-tg1-wave2.md` shows as modified in `git status`. That is the designer's §16.8 edit; I did not touch it.

## Files changed
- `benchmark/bench/p426_freeze.py`: P59, P60/P61 (freeze side), P62, the rehearsal manifest, R2's exact reason, and the freeze seams.
- `benchmark/bench/p426_wave2.py`: P63, flat make-up roots, the rehearsal date and identity, and the sequencer seam check.
- `benchmark/bench/tests/test_b2_s8_freeze.py`: `FOps` follows the new seams, old cases adapted, new tests added.
- `benchmark/bench/tests/test_b2_s8_wave2.py`: adapted and new tests, 0-based `occurrence` fixtures, a seam-less `Without` ops wrapper.
- `benchmark/bench/tests/b2_s8_support.py`: request `elapsed_s`, and a frozen `schedule.json` plus its sha256 in `chain.json` for every leg root.

## What changed, per item
- **P59:**
  - **Restore diff:** it moved out of `ops` into `default_checks`. The restore-diff test failed with `AttributeError: 'FOps' object has no attribute 'restore_diff_problems'`.
  - **Missing seams:** a missing seam is now `REFUSED: the ops seam <name> is missing`, rc 2, before any record is written (freeze) or the lock is taken (sequencer).
  - **Seams covered:** freeze checks `worktree_state`, `identity`, `build_inputs` and `historical_walls` per command. The sequencer checks `launch`, `alive`, `wait`, `power`, `harvest`, `harvest_path`, `publish_dossier`, `publish_run_files`, `operator_emails`, `worktree_state`, `identity`, plus `historical_walls` for `run`.
- **P60/P61:** v8 `settle_bound_s` is `max(900, 2 × max(R1's largest request elapsed_s, ops.historical_walls()["max_request_elapsed_s"]))`. The amendment's is `max(v8's, 2 × the pilots' largest)`. A typed bound is ignored, and missing `elapsed_s` refuses. `historical_walls()` now returns `{w_python_s, w_go_s, max_request_elapsed_s}`.
- **P62:** `production_tree_problems` runs `git diff --quiet <ref> <gitlink> -- mlx_vlm ':!mlx_vlm/tests'` in `src/mlx-vlm` for each arm, through `checks("v8", …, build, production_ref, gitlinks)`. Its test uses a real temporary git repo.
- **P63:** the plan is read from each leg's `schedule.json`, checked against the sha256 in `chain.json`; the constants and the watcher's `--planned` are gone. `classify_leg` no longer takes `planned`. The pilot gate compares rows with the frozen plan and also requires it to be 5.
- **§16.8 semantics:**
  - R2 must match `reconciliation mismatch (injected)` exactly.
  - Make-up out-roots are flat; only the occurrences files stay under `<out-base>/makeup/`.
  - `occurrence` is 0-based in the fixtures.
  - `freeze rehearsal` requires `--frozen-prompt-date` and records it plus the three identity keys from `ops.identity(off_worktree)`.
  - `p426_wave2 rehearsal` requires `--frozen-prompt-date`, refuses one that differs from the manifest's, and takes the identity from the manifest instead of calling the probe.
  - Exit codes and OVERRUN are unchanged. `overrun` is written to every leg record, and the existing test asserts `overrun: true` on an overrun leg.

## Commands and verbatim summary lines
- Red run, before any fix (the freeze and sequencer tests together; the first output cut off the summary line, so I did not capture a count):
  `../bin/run_stack_tests.sh bench/tests/test_b2_s8_freeze.py bench/tests/test_b2_s8_wave2.py` showed many failures, listed below.
- After the freeze fixes: `../bin/run_stack_tests.sh bench/tests/test_b2_s8_freeze.py` gave `62 passed in 1.19s`.
- After all fixes: the same two files gave `169 passed in 3.85s`.
- Required check run (the seven files in CHECK): `512 passed in 110.30s (0:01:50)`.

## New tests seen red first (failure line)
- Restore diff through `checks` and the default `checks`: `AttributeError: 'FOps' object has no attribute 'restore_diff_problems'` and `assert ([] == ['restore bad']`.
- `production_tree_problems` tests: `AttributeError: module 'bench.p426_freeze' has no attribute 'production_tree_problems'`.
- The `default_checks` v8 test: `AttributeError: … has no attribute 'help_problems'` (red until I split the K3 check into `help_problems`).
- Settle bound tests: `KeyError: 'python'` at `p426_freeze.py:469`, from the old `historical_walls` shape; the other settle cases failed on the same shape.
- Missing seam tests: `assert (0 == 2)`, i.e. the run proceeded instead of refusing.
- Frozen-schedule classification: `assert ('VALID' == 'INVALID'` (`test_classify_reads_the_planned_slots_from_the_frozen_schedule_never_a_constant`).
- The `--planned` test: `assert '--planned' not in [...]`.
- Flat make-up root: `assert '/…/makeup/tg1-p426-off-makeup.a1' == '/…/tg1-p426-off-makeup.a1'`.
- Rehearsal date: the freeze rehearsal tests failed with `REFUSED: unrecognized arguments: --frozen-prompt-date …`.
- Not red: `test_pilot_gate_needs_the_five_item_pilot_schedule` passed against the old code, because the old gate already reported "6 / 5 items realized". I kept it as a regression test.

## Not done
- The K3 `--help` runs, the real `git diff` against a live worktree, and `BoxOps` / `BoxSeqOps` are still not exercised on a real box. The production-tree check is tested only on a small synthetic repo.

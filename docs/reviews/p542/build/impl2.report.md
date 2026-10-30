All 75 tests in `test_p542_qualify_any.py` now pass, including the new v1.2/v1.3 ones, along with the full delivery-1 set. The production diff is empty. I did not run black or isort; no formatter is among my allowed commands. Lines I added are not all ≤ 88 columns, because several docstrings and comments follow the file's existing wide style. Nothing is committed or pushed.

## Files changed
- `dev/p369_phase2/qualify.py`:
  - The registry is read once under the run lock, right after `acquire_lock` and before preflight. The stack-HEAD start state is taken with it. Arms, the gate, derived and restored registries, hashing and execution all use those bytes. Binding checks compare against that snapshot's sha256, so a later change refuses.
  - New `certified_argv`, `argv_binding_problems`, `safe_id`, `out_path` and `_full_sha`. Each MTP-ON entry's argv, from `full_command(...)[1:]`, is compared with its P369 run's `manifest.json` `picks[name].argv_on`, naming the first differing flag.
  - Production resolves to a full sha on both sides, including the default.
  - "Served MTP-ON" now comes from `expected_config`'s drafter; a partial or non-MTP draft block refuses.
  - `mtp_off_registry` locates the keys through the YAML node marks and removes whole source lines.
  - Per-entry files and the job directory under `--out` use the safe id.
  - `arm_for` refuses a restore when the name is not in `registry_state`.
- `mlx_vlm/tests/test_p415_qualify.py`:
  - `_problems` writes a manifest beside the summary and passes `resolve`.
  - The `_drive` harness writes the certified `argv_on` into its manifest and mocks `orchestrate.resolve_production_ref`.
- `mlx_vlm/tests/test_p426_qualify_predictor.py`: the derived-registry filename now uses `qualify.safe_id`.
- `mlx_vlm/tests/test_p542_impl.py`: `_production_matches` tests updated to the new signature, plus new tests for `safe_id`, resolution failures, and the error naming the key and its 1-based line.

## Commands and results
- `../bin/run_fork_tests.sh mlx_vlm/tests/test_p542_qualify_any.py` → `75 passed, 2 warnings in 31.47s`
- `../bin/run_fork_tests.sh mlx_vlm/tests/test_p542_qualify_any.py mlx_vlm/tests/test_p415_qualify.py mlx_vlm/tests/test_p426_qualify_predictor.py mlx_vlm/tests/test_p452_qualify_in_wrapper.py mlx_vlm/tests/test_p369_phase2_*.py mlx_vlm/tests/test_p542_impl.py` → `705 passed, 1 skipped, 2 warnings in 63.50s (0:01:03)`. This was before the last test I appended.
- `../bin/run_fork_tests.sh mlx_vlm/tests/test_p542_impl.py` (after that append) → `14 passed, 2 warnings in 1.31s`
- `git diff --stat -- mlx_vlm ':!mlx_vlm/tests'` → empty

I did not rerun the full set after the last append. The skip is the same one as in delivery 1, which I never traced to a file.

## Judgement calls
- **Refusals inside the lock:** the entry, arm and gate refusals now run inside the lock, because the snapshot must be read under it. They are still `SystemExit("refused: [...]")` raised before `out.mkdir` and before any report or job.
- **Argv binding:** a mismatch is recorded as a per-entry problem in the loop, so the entry shows as FAILED and no job runs. A manifest without `argv_on` refuses up front. If the argv differs only in flag order, the message names "argument order".
- **Summary production:** it must be 7–40 lowercase hex characters. It is resolved with `_resolve_ref` in the fork and compared to the run's full sha. The run's production goes through `orchestrate.resolve_production_ref`, so the default must be a strict ancestor of the reviewed head.
- **Flow-style blocks:** the flow-style refusal message carries `<name>: <first MTP key> (line N)` rather than only the entry name. This satisfies the spec's "naming the entry" and the test's "draft_kind in message".
- **Keys that can't be removed:** any key whose line also holds other content (for example `- draft_kind: x`) or a non-comment tail refuses, naming the key and line. The existing semantic-equality guard still follows.
- **Partial draft blocks:** they refuse for every `--predictor` value, including `off`.

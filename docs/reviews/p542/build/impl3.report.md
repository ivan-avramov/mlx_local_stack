All four v1.4 defects are fixed. The full set passes and the production diff is empty. I wrote the tests first and ran them red before touching `qualify.py`. I did not run black or isort, so formatting is unchecked. Nothing is committed or pushed.

## Red first
Command: `../bin/run_fork_tests.sh mlx_vlm/tests/test_p542_impl.py`
```
FAILED mlx_vlm/tests/test_p542_impl.py::test_v14_a_summary_name_may_contain_a_slash
FAILED mlx_vlm/tests/test_p542_impl.py::test_v14_the_argv_binding_refuses_before_the_run
FAILED mlx_vlm/tests/test_p542_impl.py::test_v14_the_certified_argv_is_read_once_and_a_missing_one_has_its_message
FAILED mlx_vlm/tests/test_p542_impl.py::test_v14_merge_inherited_mtp_keys_refuse_naming_key_and_source_line
FAILED mlx_vlm/tests/test_p542_impl.py::test_v14_a_null_integer_value_refuses_the_entry_without_a_traceback
5 failed, 14 passed, 2 warnings in 2.77s
```

## Green
Command: `../bin/run_fork_tests.sh mlx_vlm/tests/test_p542_qualify_any.py mlx_vlm/tests/test_p415_qualify.py mlx_vlm/tests/test_p426_qualify_predictor.py mlx_vlm/tests/test_p452_qualify_in_wrapper.py mlx_vlm/tests/test_p369_phase2_*.py mlx_vlm/tests/test_p542_impl.py`
```
711 passed, 1 skipped, 2 warnings in 65.29s (0:01:05)
```
`git diff --stat -- mlx_vlm ':!mlx_vlm/tests'` printed nothing. There was one intermediate run with 5 failures, all in `test_p415_qualify.py`'s `_problems` helper before I updated it; that failure output is not shown here.

## Files changed
- `dev/p369_phase2/qualify.py`:
  - `summary_arguments`: `name=path` is a name when the text before the first `=` is one of the `--entry` names, so a name may contain `/`.
  - The MTP-ON argv binding runs in `drive()` after `out.mkdir` and before `_drive_locked`, so before the preflight, the report and the monitor. A mismatch raises `SystemExit("refused: [...]")`.
  - The certified argv is read once into a dict that `entry_problems` and the binding both use. A missing one refuses with `<name>: its P369 manifest.json has no picks[<name>].argv_on`.
  - `mtp_off_registry` now refuses merge-inherited MTP keys with `<name>: <key> (line N): inherited through a merge key…`. N is the key's line in the merge source.
  - `expected_config` is now a wrapper that turns `TypeError`/`ValueError`/`AttributeError` into `ValueError("<name>: <error>")`. Unknown keys still raise `UnknownKey`.
- `mlx_vlm/tests/test_p542_impl.py`: five new `test_v14_*` tests. They use the independent file's `_Rig` through an import, and that file is untouched.
- `mlx_vlm/tests/test_p415_qualify.py`: the `_problems` helper now passes `certified=` directly instead of writing a manifest.

## Judgement calls
- **MTP-ON commands:** the pre-run binding computes each MTP-ON entry's `full_command` once, and the loop reuses it. Calling it twice would double-record in the independent rig's `served` list, which its tests assert on. Non-MTP-ON arms still call it in the loop.
- **Output directory:** the pre-run binding needs the overlay file, so it runs after `out.mkdir`. A refusal leaves the `--out` directory, and for a restore its overlay file, but no `report.json`.
- **Merge keys:** a merged MTP key refuses even when the entry overrides it with its own line. The inherited value would otherwise stay visible after removal.
- **Failed argv derivation:** a `full_command` failure during the pre-run binding is a refusal naming the entry (`<name>: cannot derive the served argv: …`).

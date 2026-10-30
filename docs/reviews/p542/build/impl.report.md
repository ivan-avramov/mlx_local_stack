`qualify.py` now qualifies any entry of the stack root's committed registry, in either predictor state. All 45 independent tests pass without edits, and no test contradicts the spec. I did not run `pre-commit`, black, isort or autoflake, or the wider `dev/ci.py` gate, so formatting is unchecked. I did not commit.

## Files changed
- `dev/p369_phase2/qualify.py`:
  - Removed `ENTRIES` and the old `PRODUCTION = "7207179b"`.
  - Added `MTP_KEYS`, `serves_mtp`, the new `arm_for`, `default_entries(registry_entries)`, `mtp_off_registry`, `summary_arguments` and `_production_matches`.
  - `entry_problems`, `load_references` and the driver are rewritten.
  - `--p369-summary` is now repeatable, and the reports carry `arm`, `rates` and `overlay_sha256`.
- `mlx_vlm/tests/test_p415_qualify.py`: amended (below).
- `mlx_vlm/tests/test_p426_qualify_predictor.py`: amended (below).
- `mlx_vlm/tests/test_p542_impl.py`: new, 11 tests for rulings the independent tests don't pin.
- `registry_states.py` is untouched, and the production tree diff is empty.

## Amendments to existing tests
**`test_p415_qualify.py`:**
- **Imports and `_registry` helper:** I added `orchestrate` and `registry_states` imports, a `QWEN36_ENTRY` and a `_registry()` helper that writes synthetic registries.
- **`_with_served`:** deleted, because there is no table left to inject into.
- **`test_t1_the_three_entries_and_their_arms`:** now `test_t1_the_default_entries_are_the_registrys_picks`, since the table was removed.
- **`test_t1_a_synthetic_served_entry_takes_the_served_arm`:** now asserts `served_off` and `served_on` from the committed block.
- **`test_t1_an_unknown_entry_or_an_ungated_qwen36_refuses`:** moved to the new `entry_problems` signature through a `_problems` helper. I dropped the old `[FABLE, STATIC] == []` assertion: FABLE served ON is now gated, so it correctly produces a problem without a summary. <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
- **`test_t6_the_reference_table_loads_and_refuses_bad_rows`:** dropped the `{"not-an-entry": None}` bad row, because references no longer refuse unknown names.
- **`test_p476_the_real_reference_table_loads_against_the_real_entries`:** the subset check now uses the pinned golden fixture's registry names instead of `ENTRIES`.
- **`_drive` harness:** it now builds a real synthetic registry and writes it to `stack/main_models.yaml`. It writes a campaign-artifact P369 summary for FABLE, sets `STACK_WORKDIR`, takes a `predictor=` argument, derives the served argv from the served block, and drops the `overlay_registry`, `classify`, `fixture_text` and `yaml.safe_load` mocks. <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
- **`test_d8_the_default_run_is_all_three_and_needs_the_qwen36_evidence`:** now `test_d8_the_default_run_is_all_the_picks_and_needs_their_evidence`.
- **`_summary` and `test_d10_the_qwen36_gate_checks_the_summarys_provenance`:** `_summary` now takes the entry name and uses `orchestrate.PRODUCTION` instead of `7207179b`. The d10 parametrization and call follow the new signature.

**`test_p426_qualify_predictor.py`** is rewritten:
- **`test_the_arm_follows_the_predictor`:** now uses the new arm names and `registry_entry` / `registry_state`.
- **`test_a_served_entry_has_no_on_arm`:** renamed to `test_a_served_entry_without_a_drafter_to_restore_has_no_on_arm`, and now expects `no MTP drafter to restore`.
- **`test_the_off_arm_needs_no_p369_gate`:** uses `_problems`.
- **`test_the_off_arm_serves_the_committed_registry`:** replaced by `test_the_off_arm_serves_a_derived_registry_without_the_mtp_keys`.
- **`test_the_off_arm_refuses_a_registry_serving_the_entry_mtp_on`:** replaced by `test_the_off_arm_serves_an_entry_committed_off_as_committed`, because that guard is removed.
- **`test_the_cli_takes_on_or_off_only`:** unchanged.

`test_p452_qualify_in_wrapper.py` needed no change.

## Commands and results
- `../bin/run_fork_tests.sh mlx_vlm/tests/test_p542_qualify_any.py` → `45 passed, 2 warnings`
- `../bin/run_fork_tests.sh mlx_vlm/tests/test_p542_qualify_any.py mlx_vlm/tests/test_p415_qualify.py mlx_vlm/tests/test_p426_qualify_predictor.py mlx_vlm/tests/test_p452_qualify_in_wrapper.py mlx_vlm/tests/test_p369_phase2_*.py mlx_vlm/tests/test_p542_impl.py` → `673 passed, 1 skipped, 2 warnings`. I didn't investigate the one skip; the `test_p369_phase2_*` files are in the glob, but I didn't isolate the skip, so I can't say which file it is in.
- `git diff --stat -- mlx_vlm ':!mlx_vlm/tests'` → empty.

## Judgement calls
- **MTP-ON detection:** an entry is "served MTP-ON" if its committed block has any of the three MTP keys.
- **Restore refusals:** a restorable name needs to be in `ENTRY_OFF`. A name in `ENTRY_OFF` whose registry doesn't classify refuses with the spec's "not one of the 16 accepted states" text. Any other name refuses with "no MTP drafter to restore".
- **Refusal timing:** these refusals, the production resolution and the summary gate all run in `drive()` before `out.mkdir`.
- **Classifier timing:** the classifier is called lazily, only when `--predictor on` meets an OFF entry. The pinned fixture is loaded only for a restore.
- **Production check:** with the default production the summary must equal `orchestrate.PRODUCTION`. With `--production-ref` it must be a prefix (at least 7 hex) of the resolved sha. The default constant is not git-resolved, as before.
- **`--p369-summary` parsing:** a value counts as `name=path` only if the text before the first `=` is non-empty and contains no `/`. Otherwise it is a bare path, which is accepted for a single entry only. A duplicate for one entry refuses.
- **`mtp_off` registry:** the derived file is written to `<out>/mtp-off-<name>.yaml`. A derivation that does not parse back to "settings minus those keys" refuses. `overlay_sha256` is recorded for both `mtp_off` and `mtp_on_restored`.
- **Dropped references check:** the reference-name check was removed, so a reference for a name not in the registry is no longer refused.
- **Dropped guard:** the old `--predictor off` "registry serves it MTP-ON" guard and the whole-registry 16-state check at startup are gone.

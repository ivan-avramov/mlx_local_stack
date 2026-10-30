I added the post-review r1 tests to `test_p542_qualify_any.py`. Of the r1 tests, 22 fail against the current code and 8 pass; the amended default-production test also fails. One finding first: the `qualify.py` in this copy is still the v1.1 implementation, with none of the v1.2 bullets in it. So the failures below are the v1.2 changes not yet being there, not a regression.

I only edited the test file; `qualify.py` and the other tests are untouched, and nothing was committed or pushed. `test_p542_impl.py` (untracked) isn't mine; I didn't touch it.

## Runs (verbatim summary lines)
- `../bin/run_fork_tests.sh mlx_vlm/tests/test_p542_qualify_any.py` → `23 failed, 52 passed in 24.52s`
- `../bin/run_fork_tests.sh` on `test_p415_qualify.py`, `test_p426_qualify_predictor.py` and `test_p452_qualify_in_wrapper.py` → `106 passed in 7.56s`

Before my edits, the file's original 45 tests all passed against this implementation.

## Changes to the test setup
- **Real production refs.** `--fork-root` is now a temp git repo with commits P0 → P → R. R is the reviewed head, and `orchestrate.PRODUCTION` is patched to P's 8-hex short sha, the same shape as the real constant. `_resolve_ref` and `resolve_production_ref` are no longer mocked, so refs resolve through real `git rev-parse`.
- **`binding_problems`.** The mock now does the real check's registry half (the file's sha against the run's `registry_sha`). Without this, no registry change would be visible.
- **`argv_on` in summaries.** Summaries write `manifest.json` with `picks[name].argv_on`, taken from the committed block or the 16-state overlay.
- **Amended tests.** `test_c3_a_summary_on_the_default_production_passes` now uses the realistic shape you asked for: a short default and a summary that records the full sha. `test_c3_a_summary_must_match_the_runs_production_ref` now uses the real commit P0 instead of `"c"*40`.

## r1 tests that fail now, and why (all on missing v1.2 behaviour)
| Test | v1.2 bullet | Why it fails now |
|---|---|---|
| P38 `test_c3_a_summary_on_the_default_production_passes` (amended) | production | The full-sha summary is refused, because v1.1 checks the summary sha is a prefix of the short default |
| P39 `test_r1_a_registry_flipped_on_after_the_gate_refuses[acquire_lock, preflight]` | snapshot | The gate sees Fable OFF, the file flips to ON, and the MTP-ON job runs ungated to COMPLETED | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P40 `test_r1_a_registry_changed_between_the_gate_and_execution_refuses` | snapshot | Another entry's block changes at preflight and the run still completes |
| P41 `test_r1_an_mtp_on_argv_differing_from_the_certified_one_refuses_naming_the_flag` (4 cases: `--kv-bits` changed or added, `--draft-model` on served ON and on a restore) | argv binding | `argv_on` is ignored, so every case completes |
| P42 `test_r1_a_p369_manifest_without_the_entrys_argv_refuses` | argv binding | Completes |
| P43 `test_r1_an_unresolvable_default_production_refuses` | production | The default is never resolved, so a non-commit `0123abcd` summary passes |
| P44 `test_r1_a_partial_or_non_mtp_draft_block_refuses` (no `draft_model` / scan only / `draft_kind: suffix`) | served MTP-ON | Any MTP key counts as served ON, so the run completes with drafter False |
| P45 `test_r1_mtp_off_removes_quoted_and_differently_indented_keys` (quoted / indented) | `mtp_off` removal | The regex misses both, and it refuses with `the MTP keys could not be removed textually` |
| P46 `test_r1_an_mtp_key_that_cannot_be_removed_names_the_key` | `mtp_off` failure message | It refuses, but the message doesn't name `draft_kind` |
| P47 `test_r1_per_entry_paths_use_a_safe_id_under_out` (6 cases) | safe ids | `served_off`: the job dir is the raw name (`org/Model-X-4bit`); `/abs/…` and `../…` resolve outside `--out`. `mtp_off`: `FileNotFoundError` writing `mtp-off-<name>.yaml` |
| P48 `test_r1_arm_for_refuses_a_restore_when_the_name_is_not_off_in_registry_state` | `arm_for` | `DID NOT RAISE ValueError`: v1.1 only checks the state is not None |

## r1 tests that pass now (regression guards)
- **P49** The snapshot test with the change injected at `interference` passes. The change lands after the second registry read, and the `binding_problems` sha check already fails the entry.
- **P50** `test_r1_an_mtp_on_arm_runs_when_its_argv_equals_the_certified_one` passes because v1.1 ignores `argv_on`.
- **P51** `test_r1_a_short_summary_matches_a_full_run_ref` and `test_r1_a_full_summary_matches_a_short_run_ref` pass. v1.1's prefix rule plus `resolve_production_ref` already handle both.
- **P52** `test_r1_a_summary_on_another_commit_refuses` and `test_r1_an_unresolvable_production_refuses[run-ref, summary]` pass. v1.1 already refuses these.
- **P53** `test_r1_a_failed_entry_with_a_record_carries_rates_and_arm` passes. v1.1 already records `rates`/`arm` whenever a record exists.

## Points v1.2 leaves open (I assumed, did not resolve)
- **P54 Where the snapshot is read relative to preflight.** Only the "flipped ON" cases are certain to refuse whichever way it's done. A comment-only change at preflight refuses only if the read comes before preflight, so I didn't test that case.
- **P55 What the safe id looks like.** The tests require one path component under `--out`, `[A-Za-z0-9._-]` only, containing the sha256(UTF-8 name)[:8]. They don't fix the separator or the order.
- **P56 "Names the key and its line".** The tests check only the key name. A line number versus the line's text is unspecified.
- **P57 The flow-style block.** I assumed it is something the removal cannot do, so it should refuse. v1.2 could instead be read as editing inside the line.
- **P58 What "first differing flag" means** when the certified argv has an extra flag (`--kv-bits` added). The tests only check that the flag's name appears in the message.

The file isn't black-formatted (a few lines are over 88 columns); black wasn't in the allowed commands, so the gate's pre-commit step will want to run it.

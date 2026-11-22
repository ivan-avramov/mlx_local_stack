# Test-writer report, delivery 1 — S29 record-not-block

Baseline `204a8da16ac301c8a98cceec69a9a8af91d3b12d`. Tests only; no production file, no existing test, no instruction file touched.
Nothing committed or pushed. New files, all in `benchmark/bench/tests/s29_frozen/`:

| file | content |
|---|---|
| `__init__.py` | package marker |
| `s29_support.py` | fixtures: real `host_env.fingerprint()/diff()` worlds, the a3-shaped `leg.json` builder (`make_a3`), record-search helpers |
| `test_s29_host_sequencer.py` | H1, H2, H3, baseline invariants (17 tests) |
| `test_s29_host_positives.py` | H4 (9 tests) |
| `test_s29_h5_rederive.py` | H5 + the resume trace + consumers (12 tests) |
| `test_s29_harvest.py` | P6a, P6b, every refusal that stays (31 tests incl. parameters) |
| `test_s29_oracles.py` | the record-search helpers checked against a known positive and a known negative (3 tests) |

## Command and result on the baseline

```
../fe_test.sh stack bench/tests/s29_frozen --tb=no
```
Summary line, verbatim: `52 failed, 20 passed in 11.32s`

(72 tests = 17 + 9 + 12 + 31 + 3.) The 20 that pass on the baseline are the invariants and instrument controls; every one of them
is listed below as "pass". Causes of failure, from the captured output of the runs I read (sequencer, positives, harvest; the rest
by the same path): the sequencer ones stop at the C360 refusal ("STOP: the host environment differs from the run's baseline ..." or
"is INVALID: host environment changed ..."), the positives ones at `problems` / `verdict FAIL` / rc 1, the harvest ones at the recorded
refusal text (`no harvest rule matches this file ... referenced file ... is missing`, the a3 line verbatim). I did not read the
failure text of every one of the 52 individually; none that I read is a fixture error. The H5 group fails on the baseline at the host
refusal of the resumed run, BEFORE it reaches the INVALID-leg stop the spec describes, so the baseline run does not show that
second failure; the first delivery's fixtures are exercised on it only up to that point.

**Limit of this evidence:** no FIX / NEW test has been seen to PASS, because no implementation exists yet; they are seen to fail on
the baseline for the intended reason and their search helpers are checked in `test_s29_oracles.py`, but a wrong assertion that only
bites on a correct implementation (e.g. a wording, the H5 fixture after the fix) can still be in them. Delivery 2 (the implementation)
is the first check of that; expect to correct the tests that turn out over-specific, and list each correction.

## Tests, class, baseline outcome

Class: FIX = reproduces a failure the spec fixes; INV = preserves an invariant; NEW = exercises new behaviour.

### `test_s29_host_sequencer.py` (driver: the frozen B2 sequencer fakes + `HostWorld`; the Cellar/npm dir is mutated at launch / harvest seams)
| test | class | baseline |
|---|---|---|
| `test_fix_h1_a_host_change_before_a_launch_is_logged_recorded_and_the_leg_launches` (H1; spec trace: log `host environment differs from the baseline before <leg>: …`, leg launches, `leg.json` and sequence entry carry the diff, VALID) | FIX | fail |
| `test_fix_h1_a_resumed_run_on_a_changed_host_logs_the_diff_and_goes_on` (H1 via `host_env_start`; baseline file not rewritten) | FIX | fail |
| `test_inv_h1_an_unchanged_host_records_no_host_change_anywhere` | INV | pass |
| `test_fix_h2_a_change_during_a_leg_is_recorded_in_leg_json_and_the_leg_stays_valid` | FIX | fail |
| `test_new_h2_leg_json_tells_what_differed_at_launch_from_what_changed_during_the_leg` (JDK before launch, jest during: both in `leg.json`, different containers) | NEW | fail |
| `test_fix_h2_the_state_reason_and_class_come_only_from_classify_leg[crashed-chain…]` (stays INVALID, reason `chain rc 2, status 'finished'`, no host phrase, no `(prior …)`) | FIX | fail |
| `…[settled-dnf…]` (stays `VALID_WITH_DNF` / class `dnf` / reason `1 transport DNF, settled`) | FIX | fail |
| `test_fix_h2_a_crashed_chain_is_still_stopped_for_its_own_reason_not_the_host` | FIX | fail |
| `test_fix_h2_a_leg_upgrade_never_makes_the_next_rerun_refuse` | FIX | fail |
| `test_fix_h3_a_change_after_the_last_leg_is_recorded_logged_and_the_run_completes` (rc 0, `DONE`, in `sequence.json` before every publication) | FIX | fail |
| `test_fix_h3_a_change_after_the_through_leg_is_recorded_and_the_run_stops_as_asked` | FIX | fail |
| `test_inv_h3_an_unchanged_end_records_nothing_and_returns_as_before` | INV | pass |
| `test_inv_h3_an_exception_in_the_leg_region_logs_the_diff_and_still_propagates_as_itself` | INV | pass |
| `test_fix_h3_after_leg_no_longer_stops_on_a_host_reason` (unit: `Sequencer.after_leg`, a rehearsal leg expecting INVALID, host reason) | FIX | fail |
| `test_inv_the_baseline_is_first_check_and_never_rewritten_by_a_host_change` (`host_env.json` byte-identical) | INV | fail (the scenario needs the run to continue past a change) |
| `test_inv_an_unreadable_or_tampered_baseline_still_stops_before_any_launch[garbage, tampered-fingerprint]` | INV | pass ×2 |

### `test_s29_host_positives.py` (H4; `s26_support.PosOps` over a temp host)
| test | class | baseline |
|---|---|---|
| `test_fix_h4_a_host_change_during_the_positives_is_recorded_and_the_record_passes[grade, inject, session_exit]` (PASS, `problems == []`, rc 0, sealed; the change is in the record outside the raw fingerprints) | FIX | fail ×3 |
| `test_fix_h4_the_v8_freeze_accepts_a_positives_record_that_carries_a_host_change` (`p426_freeze.positives_problems`) | FIX | fail |
| `test_inv_h4_the_v8_check_used_above_accepts_a_clean_record` (instrument control) | INV | pass |
| `test_fix_h4_each_host_change_is_recorded` | FIX | fail |
| `test_fix_h4_an_exception_and_a_host_change_the_exception_alone_fails_the_record` | FIX | fail |
| `test_fix_h4_a_failed_positive_still_fails_the_record_with_a_host_change_beside_it` (problems equal those of an unchanged-host twin run) | FIX | fail |
| `test_inv_h4_an_unchanged_host_passes_with_no_host_change_recorded` | INV | pass |

### `test_s29_h5_rederive.py` (H5; `make_a3` writes the a3 shape — `chain_rc` 0, class systemic, reason with the host phrase and no prior, sealed by `ph.write_exclusive`, sequence INVALID, not harvested — then resumes WITHOUT `--rerun`)
| test | class | baseline |
|---|---|---|
| `test_inv_h5_the_consumer_checks_accept_a_plain_valid_leg` (instrument control for the consumer view: sequence, `fz.read_leg` / `valid_leg_problems`, `V._leg_reasons`, `SG._coverage`) | INV | pass |
| `test_fix_h5_the_resumed_run_rederives_the_state_harvests_and_goes_on_to_the_next_leg` (resume trace: no launch of the leg, no rerun entry, harvested, next leg launches) | FIX | fail |
| `test_new_h5_the_rederived_record_has_the_new_state_the_host_changes_and_the_supersession_and_verifies` (VALID / valid / "", host changes, original sha256, "C384", seal verifies) | NEW | fail |
| `test_new_h5_the_original_sealed_leg_json_is_kept_byte_identical_and_is_harvestable` (some other file holds the original bytes; present at harvest time; `H.classify("leg", name)` copies it) | NEW | fail |
| `test_new_h5_every_consumer_sees_the_new_state` (sequencer, freeze, verify rule 1, signals A7, no leg.json/sequence.json mismatch) | NEW | fail |
| `test_inv_h5_the_run_baseline_is_not_rewritten` | INV | fail (scenario needs the resume to run) |
| `test_inv_h5_a_second_resume_finds_the_leg_done_and_changes_nothing` | INV | fail (same) |
| `test_inv_h5_a_leg_with_a_prior_reason_is_left_as_recorded` | INV | fail (see note 1) |
| `test_inv_h5_a_harvested_leg_is_left_as_recorded` | INV | fail (see note 1) |
| `test_inv_h5_a_reason_that_is_not_the_host_change_is_left_alone` | INV | fail (see note 1) |
| `test_fix_h5_when_the_recorded_chain_is_not_clean_the_leg_stays_invalid_with_classify_legs_reason` (`chain rc 0, status 'aborted'`, host changes + original sha beside it) | FIX | fail |
| `test_fix_h5_the_recorded_overrun_flag_gives_the_overrun_state_when_the_chain_is_not_clean` (OVERRUN rule with the recorded `overrun`) | FIX | fail |

Note 1: the three "left as recorded" tests assert, besides unchanged bytes, that the run stopped ON THE LEG (`<leg>.a1` in the log, no
`STOP: the host environment differs`). On the baseline the resumed run stops at the host refusal first, so they fail there; without
that assertion they would pass vacuously on the baseline (nothing changes when the run stops at once). They discriminate after the fix.

### `test_s29_harvest.py` (P6a, P6b; `test_b2_s9_harvest.World` + the real `harvest_wave2`; the marker is the recorded 34-byte `TG2_RUNNER_START …`)
| test | class | baseline |
|---|---|---|
| `test_fix_p6a_the_grader_marker_in_a_tg2_grade_dir_is_evidence_and_the_leg_harvests` (a3 refusal reproduced verbatim on the baseline) | FIX | fail |
| `test_fix_p6a_a_marker_is_scrubbed_like_the_other_grade_outputs` | FIX | fail |
| `test_fix_p6a_a_marker_with_the_operators_address_is_quarantined_not_published` | FIX | fail |
| `test_fix_p6a_a_marker_with_a_credential_is_quarantined_not_published` | FIX | fail |
| `test_fix_p6a_a_marker_is_evidence_only_directly_in_a_grade_seq_dir[no-seq-dir, too-deep, seq-digits, seq-suffix, flat, no-language, no-grades-suffix]` (harvest goes on, not copied, listed) | FIX | fail ×7 |
| `test_fix_p6a_a_marker_in_the_leg_root_is_not_evidence` | FIX | fail |
| `test_fix_p6b_an_unrecognised_file_is_listed_not_copied_and_the_harvest_succeeds[leg, evidence, run]` (path, size, sha256; `HARVEST.json` self-hash; idempotent second call) | FIX | fail ×3 |
| `test_fix_p6b_the_listing_carries_no_box_path` | FIX | fail |
| `test_fix_p6b_a_path_that_names_the_operator_account_is_scrubbed_in_the_listing` (edge; assumption) | FIX | fail |
| `test_fix_p6b_a_row_reference_to_an_unrecognised_file_is_listed_and_not_refused` | FIX | fail |
| `test_fix_p6b_the_a3_leg_harvests_with_its_marker_and_a_second_unknown_file` | FIX | fail |
| `test_inv_the_marker_rule_does_not_loosen_the_other_grade_outputs` | INV | fail (it also holds an unrecognised file, which the baseline refuses) |
| `test_inv_a_credential_in_a_recognised_file_still_quarantines_the_harvest[alone]` / `[beside-an-unrecognised-file]` | INV / FIX | pass / fail |
| `test_inv_a_main_record_the_scrub_would_change_still_refuses[alone]` / `[beside-…]` | INV / FIX | pass / fail |
| `test_inv_a_reference_outside_the_inventoried_roots_still_refuses` | INV | pass |
| `test_inv_a_reference_to_a_file_that_does_not_exist_still_refuses` (assumption, see below) | INV | pass |
| `test_inv_a_symlink_outside_a_final_tree_still_refuses_even_when_it_is_named_like_a_marker` | INV | pass |
| `test_inv_a_non_regular_file_still_refuses` (FIFO) | INV | pass |
| `test_inv_an_immutable_record_without_a_valid_self_hash_still_refuses[wrong, missing]` | INV | pass ×2 |
| `test_inv_a_leg_without_leg_json_still_refuses` | INV | pass |

### `test_s29_oracles.py`
Three INV tests, all pass: the container finder separates two changes whatever the field names (and flags one field holding both);
the listing finder finds a listed file and misses another digest / size / path / absent listing; the copy finder finds a copy.

## Existing modules run on the baseline (acceptance 3 reference)
Run (read-only, baseline, nothing of mine imported by them):
```
../fe_test.sh stack bench/tests/s26_frozen bench/tests/test_s26_impl_sequencer.py bench/tests/test_s26_impl_positives.py bench/tests/test_b2_s9_harvest.py bench/tests/test_b2_frozen_s9_harvest.py bench/tests/test_p586_impl_harvest.py bench/tests/p586_frozen/test_p586_harvest.py --tb=no
```
Summary line, verbatim: `1 failed, 449 passed in 386.97s (0:06:26)`. (The same set without the two `test_b2_*s9_harvest` modules, run separately: `1 failed, 292 passed in 363.17s (0:06:03)`.)

The one failure is on the baseline and is not caused by this delivery:
`bench/tests/s26_frozen/test_s26_positives.py::test_fix_an_exception_message_never_carries_the_absolute_home_path` asserts the real home
path is absent from the whole positives record, but the record carries the temp host's fingerprint (`host_env`, bin-dir keys) and
the temp host lives under `tmp_path`, which in this copy is below the account's home. It is environment-dependent (fails when the
scratch directory is under `$HOME`). Re-run: `../fe_test.sh stack bench/tests/s26_frozen/test_s26_positives.py -k absolute_home_path`
(1 failed). Worth knowing for acceptance 3 ("nothing else fails that passed on the baseline"): it fails on the baseline too.

NOT run: the freeze, signals and verify modules named in acceptance 3 (`test_p426_*` / `test_m76_b4b*` families) and the sequencer
modules other than the above. The `test_b2_frozen_s9_harvest.py` module runs the CLI as a subprocess per test and is slow (several
minutes). A stray `.venv-bench` entry shows in `git status` (created by the test runner, not by me).

## Existing tests that pin the old refusals (acceptance 2: to be changed by the implementer, each with why) — NOT changed by me
Found by reading and grepping; each fails (or loses its premise) once a host change stops refusing / an unknown file stops refusing.
- `bench/tests/s26_frozen/test_s26_sequencer.py`: `test_fix_a_host_change_between_legs_refuses_the_next_launch`,
  `test_fix_a_resumed_run_on_a_changed_host_stops_before_launching`, `test_fix_a_leg_that_changed_the_host_is_invalid_systemic_with_the_diff_as_reason`,
  `test_fix_several_changes_are_joined_with_semicolons`, `test_fix_a_prior_reason_is_kept_in_parentheses`, `test_fix_a_settled_dnf_leg_is_not_spared`,
  `test_fix_a_rerun_after_an_invalid_host_leg_refuses_until_the_host_equals_the_baseline`, `test_fix_a_change_after_the_last_leg_is_caught_before_the_run_files_are_published`,
  `test_fix_a_change_after_the_through_leg_is_caught_on_the_through_exit`, `test_fix_the_kv_lever_sequencer_guards_the_host_too`
  (why: they assert the C360 refusal / INVALID-by-host / stop). `test_inv_the_pre_launch_check_comes_after_the_power_check` keeps its power-first
  intent but its premise (a host refusal that loses to the power refusal) is gone: probably passes unchanged, re-read it.
- `bench/tests/s26_frozen/test_s26_round2.py`: `test_fix_the_host_invalid_leg_stop_is_a_flat_fail_closed_statement`,
  `test_fix_the_other_guard_stops_carry_no_operator_wording` (the stops they word-check no longer exist).
- `bench/tests/s26_frozen/test_s26_positives.py`: `test_fix_a_host_change_anywhere_in_the_leg_fails_the_record[grade, inject, session_exit]`,
  `test_fix_each_host_change_is_its_own_problem`, `test_fix_an_exception_and_a_host_change_are_both_recorded` (host change as a `problems` line / FAIL).
- `bench/tests/test_s26_impl_sequencer.py`: `test_a_change_between_legs_refuses_the_next_launch`, `test_a_change_during_a_leg_makes_it_invalid_systemic_harvested_and_stops`,
  `test_the_prior_reason_is_kept`, `test_a_resumed_run_on_a_changed_host_refuses_until_the_host_equals_the_baseline`,
  `test_the_end_of_run_check_runs_before_the_run_files_are_published`, `test_a_host_change_stops_even_a_leg_whose_invalid_state_is_expected`,
  `test_the_invalid_leg_stop_is_a_flat_fail_closed_statement`.
- `bench/tests/test_s26_impl_positives.py`: `test_a_host_change_during_the_positives_is_a_fail`.
- `bench/tests/test_b2_s9_harvest.py`: `test_an_unmatched_file_fails_the_harvest_and_names_it`, `test_an_unmatched_file_in_a_named_run_directory_fails_too`,
  `test_a_harvest_error_prints_one_refused_line_exits_2_and_publishes_nothing` (uses `stray.unknown-kind` as its refusal: needs another refusal, e.g. a quarantined file),
  `test_dry_run_collects_scrub_and_secret_problems_with_inventory_ones` (expects the stray file among the dry-run problems).
- `bench/tests/test_b2_frozen_s9_harvest.py`: `test_new_an_unmatched_file_fails_the_harvest`.
- `bench/tests/p586_frozen/test_p586_harvest.py`: the dry-run tests built on `_problem_world` (three files without a rule are expected as problems; `NEEDLES`).
- `bench/tests/test_m76_b4b1_impl_wave2.py::test_every_file_of_the_recorded_trees_is_classified` and `test_the_grade_sequence_rules_are_bounded_by_the_directory`
  check `classify` (closed table) on recorded trees: read them for a marker file in the recorded zebra tree.
Not verified by running (listing is from reading); the implementer's run of the named modules is the check.

## Assumptions where the spec is free (the tests assert outcomes; where an outcome needed a shape I say so)
1. **Driver.** There is no fake chain for tg2 legs (`write_leg` writes tg1 roots). H1–H5 run on the shared `Sequencer` through the tg1 driver with tg1 leg names; the tg2-only path (`after_leg` → `ensure_recheck`, `tg2-m76-x-s1` names, the `.grades` layout in a real leg) is not exercised end to end. The a3 shape (`chain_rc` 0, reason without prior, class systemic, INVALID, unharvested) is reproduced; the `.grades/seq-0002` layout is exercised in the harvest tests.
2. **Findability, not field names.** A host change is "in the record" when `host_env.diff`'s text for it (e.g. `Homebrew Cellar: added openjdk@17/17.0.9`) occurs in it. Positives: outside the two raw fingerprints (`host_env`, `host_env_after`) and outside `problems`.
3. **H2 containers.** "tell what differed at launch from what changed during the leg" = the two diffs sit in different containers of `leg.json` (distinct parent paths; no leaf holds both). A design that tags one list with "before:" / "during:" prefixes would fail this test; say so if that is intended.
4. **H1 log phrase** taken from the spec's success trace: `host environment differs from the baseline before <leg>: <changes>` (a prefix match); `STOP: the host environment differs` must be absent.
5. **H5.** "the record every consumer reads" = `<leg root>/leg.json`; the original is kept under another name found by its bytes; the new record names the original's sha256 and contains the literal `C384`; the original's file must have a `classify("leg", …)` rule (otherwise P6b lists it instead of harvesting it). "Not yet harvested" = no entry for the attempt in `sequence.json` `harvested`.
6. **P6b "listed".** Some record inside `HARVEST.json` mentions the file's path and holds its sha256 and byte size; "reference listed" = some dict other than the document root mentions both the referencing file (`rows.jsonl`) and the unrecognised file (weak: a single container dict holding both lists satisfies it). The path goes through the scrub (the user-named-directory test); that is my reading of "portable form".
7. **A reference to a file that does not exist at all stays refused** (the spec lists only "references outside the inventoried roots" by name; I read "every other harvest refusal … unchanged" to cover it).
8. **OVERRUN** is tested only through the re-derivation (recorded `overrun` true + unclean chain); the live deadline path is not exercised.

## Gaps and points for the designer
- The H5 harvest of the kept original cannot be run for real in this delivery (on the tg1 fake root the real `harvest_wave2` refused `receipt.json` with "PII: absolute home path with a username" in this environment, where tmp paths lie under a home directory; I did not pursue it). Delivery 2 can add a real `harvest_wave2` of an implementation-produced root.
- Unpinned: whether the re-derived `leg.json` keeps the recorded `started` / `ended` / `speed_valid` / `speed_reason`, and the re-derivation's log line; the spec does not say and the tests do not assert them.
- P6b listing records the sha256 and size of a file the gate never read (not scanned, not copied). A short or low-entropy secret in an unrecognised file would be guessable from the published digest, and a file NAME is published after the scrub only. Listing needs an owner decision or a gate scan before listing.
- P6b turns the closed rule table into an open one at the leg level: a new grader product that a row references is now recorded, not published; nothing in `p426_verify` / `p426_signals` reads the listing. Worth one sentence in the spec (who reads the list).

# Implementer report, fix round 1: S29 record-not-block (candidate 2)

Baseline `204a8da16ac301c8a98cceec69a9a8af91d3b12d`. Spec `docs/specs/s29-record-not-block.md` v1.1 (read-only, not edited).
Candidate 1 was already applied and staged. Nothing committed. Export: `out/candidate-2.diff` (1967 lines, 14 files; the
s29_frozen directory is excluded).

## Files changed in this round

- `benchmark/bench/p426_harvest.py`: items 1 and 4 (and the module docstring).
- `benchmark/bench/p426_wave2.py`: items 2, 3, 5 and 7.
- `benchmark/bench/tests/s26_frozen/test_s26_sequencer.py`: item 6.
- `benchmark/bench/tests/test_s29_impl_harvest.py`: new tests for items 1 and 4. My own round-1 tests that pinned a digest in the
  listing are updated to v1.1.
- `benchmark/bench/tests/test_s29_impl_sequencer.py`: new tests for items 2, 3 and 5.

No other file was touched: not `p426_freeze.py`, `p426_signals.py`, `p426_verify.py`, `host_env.py`, the spec or the frozen tests.

## Findings: fix and test

**1. P6b listing without digests, scrubbed paths** (`p426_harvest.py`)
- `Unrecognised.records(scrub)` now returns `[{source, size}]`. `source` is `scrub.text(<portable source>)`, and the sha256 of the
  unscanned bytes has been removed.
- `Unrecognised.ref_records(scrub)` now returns `[{reference, source, sha256_matches}]`, with `reference` and `source` scrubbed.
  The recorded digest is no longer stored. `_ref` still compares it and keeps only the boolean (`None` when the reference
  records no digest).
- The CLI `UNRECOGNISED:` line drops the sha256: `UNRECOGNISED: <source> (<n> bytes): no harvest rule; listed in HARVEST.json,
  not copied`.
- A path the scrub changes is therefore already in scrubbed form inside `HARVEST.json`. The final `HARVEST.json` gate no longer
  sees it as "not portable" and does not refuse.
- Tests (`test_s29_impl_harvest.py`):
  - `test_p6b_nothing_derived_from_an_unrecognised_files_bytes_is_published`: no digest of either unrecognised file appears
    anywhere in the published `HARVEST.json`. Listing keys are exactly `{source, size}` and references carry no `sha256`.
  - `test_p6b_a_listed_path_the_scrub_would_change_is_listed_scrubbed_and_never_refuses`: a file under `b2opuser/` (the
    operator account). The harvest succeeds, the listing is scrubbed, and the idempotent second call returns the same record.
  - `test_p6b_a_reference_to_a_scrubbed_path_is_listed_scrubbed`: unit test of both record methods.
  - My round-1 tests updated to v1.1: `..._row_reference_are_listed_not_refused`, `..._in_every_root_are_listed`,
    `..._digest_differs_is_listed_with_the_mismatch` (now `sha256_matches is False` with no digest field), and
    `test_p6b_the_cli_logs_the_unrecognised_files`.
  - Before the fix: 7 failures in this group (the 4 updated tests and the 3 new ones). After: all pass.

**2. H5 committed-harvest window** (`p426_wave2.py`, `Sequencer.c384_supersede`)
- After the "already harvested" check, the code now checks `os.path.lexists(Path(self.ops.harvest_path(name)) / "HARVEST.json")`.
  If the file exists, it logs `<attempt>: INVALID by the host change and its harvest is already committed; left as recorded` and
  returns without changing anything. The leg then takes the existing INVALID path (stop: a rerun is an operator decision).
- The check is existence only, as the brief states. Any file at that path blocks the rewrite (fail-closed).
- Test: `test_h5_a_committed_harvest_without_a_harvested_entry_is_left_as_recorded`. `leg.json` stays byte-identical, no
  `leg.c360.json` is written, the entry stays INVALID, rc 1 and the line is logged. It failed before the fix (rc 0, superseded)
  and passes after.

**3. H5 atomic kept original** (`p426_wave2.py`, new module functions `install_kept` and `kept_temp`)
- `install_kept` works in this order:
  1. Removes a stale `.leg.c360.json.tmp` (ours, never at the final path).
  2. Creates the temp file (`O_EXCL|O_NOFOLLOW`), writes it and fsyncs it.
  3. Runs `os.link(tmp, leg.c360.json)`. An existing file is never replaced; on `FileExistsError` the caller compares it.
  4. Unlinks the temp and fsyncs the directory.
- `c384_check_kept` calls `install_kept` when the final path is absent. It also removes a temp left by a crash between the link
  and the unlink. It still compares the final file (an equal file is accepted; a different one, a symlink or an unreadable file
  stops with rc 1, as before).
- Tests:
  - `test_h5_a_crash_while_writing_the_kept_original_leaves_no_partial_file_and_resumes`: a crash at the fsync while the kept
    original is written leaves no file at the final path, and the next resume completes with no temp left. Before the fix the
    file existed at the final path.
  - `test_h5_the_kept_original_is_installed_without_replacement`: the final path is created by `os.link` from the same
    directory.
  - `test_h5_a_crash_after_the_link_before_the_temp_is_removed_resumes`: the final file is complete, and the resume finishes
    and cleans the temp.
  - The existing tests `..._a_stop_between_keeping_the_original_and_replacing_leg_json_resumes` (an equal file is accepted) and
    `..._a_kept_file_that_is_not_the_original_stops` still pass.

**4. H5 link check in the harvest** (`p426_harvest.py`, new `_check_supersession`, called from `harvest_wave2` right after the
leg record's attempt check)
- When `leg.json` has a `c384` key, the harvest requires all of the following, and adds a problem (refusal) otherwise:
  - the key is a dict with a string `superseded_file_sha256`;
  - `leg:leg.c360.json` is in the inventory as a `main` entry (so it is a regular file of the leg root; a symlink was already
    refused by the inventory);
  - its bytes hash to `superseded_file_sha256`;
  - it passes `_immutable_problem` (its sha256 is present and equals its self-hash).
- Tests:
  - `test_h5_a_superseding_leg_json_without_its_kept_original_refuses`, 5 cases: `missing`, `other-bytes` (a sealed,
    self-hash-valid record that is not the original), `no-file-sha`, `not-a-dict` and `symlink`. All refuse and publish nothing.
    Before the fix, 4 of them did not refuse; the symlink case already refused through the inventory.
  - `test_h5_the_supersession_link_check_passes_with_the_kept_original` and the updated
    `test_h5_the_kept_original_is_harvested_as_a_main_record_beside_the_new_leg_json` (it now carries `superseded_file_sha256`
    through a helper `superseding()`) both pass.

**5. H3b end-of-run record** (`p426_wave2.py`, `Sequencer.host_env_final`)
- `host_env_after_last_leg` is now written on every final check once it exists, including `[]`, and the change is logged: "host
  environment equals the baseline after the last leg (the earlier difference is superseded)".
- A run that never differed still has no field, so the existing invariant tests still hold:
  `s26_frozen/test_s26_sequencer.py::test_inv_an_unchanged_end_publishes_logs_and_returns_as_before` and
  `test_s26_impl_sequencer.py` line 59.
- Test: `test_h3b_a_resumed_run_that_ends_on_the_baseline_overwrites_an_earlier_final_diff`. A `--through 2` run ends with
  `[JDK17]`; the JDK is then removed and the resumed run ends with `[]`. It failed before the fix (the stale `[JDK17]` stayed)
  and passes after.

**6. `test_fix_the_kv_lever_sequencer_guards_the_host_too`** (`s26_frozen/test_s26_sequencer.py`)
- The `pytest.raises(KeyError, match="n16_worktree")` pin is gone. `Sequencer.process` is now monkeypatched to record the leg it
  reached and raise a test-local `Reached`.
- The test asserts that the resumed kv run reached `tg1-m76-n16-pilot`, so it got past the host check without stopping. The
  existing log and record assertions are kept: the `at the run's start` line, `host_env_events == [[ADDED]]`, and no host STOP.
  The docstring says why `process` is stubbed. It passes.

**7. Nits**: `latest = (…` and `done = latest[…` in `process()`.

Declined items, not implemented, as the brief says: refusing on a digest mismatch of an unrecognised reference; a refusal for a
loose file in a `.final_tree`; limiting the reference relaxation to row references.

## Commands and results

All runs used `../fe_test.sh stack …` from the copy root. Counts come from `--junitxml` files in `impl/scratch/` (the runner
prints no summary line).

1. Failing first, on candidate 1 before any code change:
   - `bench/tests/test_s29_impl_sequencer.py -k "committed or crash or without_replacement or h3b"`: 5 failed, each for the
     intended reason (rc 0 instead of 1; the kept file at its final path; no `os.link`; no crash after the link; the stale
     `[JDK17]`).
   - `bench/tests/test_s29_impl_harvest.py`: 11 failed (items 1 and 4, including my 4 updated round-1 tests); the rest passed.
2. After the fixes: `bench/tests/test_s29_impl_sequencer.py bench/tests/test_s29_impl_harvest.py bench/tests/test_s29_impl_positives.py`
   → all pass (53 tests).
3. `bench/tests/s29_frozen` → **72 tests, 22 failed, 50 passed**. All 22 are contradictions with v1.1 (next section). The
   candidate-1 failure `test_fix_p6b_a_path_that_names_the_operator_account_is_scrubbed_in_the_listing` now **passes**.
4. The previous round's final module list plus my three modules: `test_s29_impl_{sequencer,harvest,positives}.py
   test_s26_impl_sequencer.py test_s26_impl_positives.py s26_frozen test_p426_harvest.py test_s27_impl_harvest.py
   test_m76_b4b1_impl_wave2.py test_m76_b4b1_fe_wave2.py test_m76_b4b2_impl_verify.py test_m76_b4b2_impl_signals.py
   test_b2_s9_harvest.py test_b2_frozen_s9_harvest.py test_p586_impl_harvest.py p586_frozen test_b2_s8_wave2.py`
   → **994 tests, 1 failed**.
   - The failure is `s26_frozen/test_s26_positives.py::test_fix_an_exception_message_never_carries_the_absolute_home_path`, the
     pre-existing, environment-dependent failure: this harness's TMPDIR is under the home directory. It also fails on the
     baseline, as the round-1 report shows.
   - Round 1 had 980 tests (979 passed, 1 failed). The +14 are this round's new tests.
5. Final re-check after the docstring-only edits: `test_s29_impl_* s29_frozen s26_frozen/test_s26_sequencer.py` → 156 tests,
   22 failed. They are exactly the 22 frozen contradictions; nothing else failed.
6. The other test modules that import `p426_wave2` / `p426_harvest` (44 modules plus `p586_frozen/test_p586_fix_round.py` and
   `p613/`) → **1739 tests, 0 failed, 0 errors, 2 skipped** (exit code 0). These ran on the final code, after the docstring edits.

## Frozen tests that contradict spec v1.1 (reported, not satisfied)

**A. The P6b digest (14 tests, expected by the brief).** `test_s29_harvest.py`'s helper `listing()` only accepts a record that
carries the file's sha256 **and** its size. v1.1 P6b says "nothing derived from its unscanned bytes, so no digest". Every test
that calls `listing()` fails at that assertion and nowhere else (the harvest succeeds, the file is not copied, and the path and
size are listed):
- `test_fix_p6a_a_marker_is_evidence_only_directly_in_a_grade_seq_dir` (7 params),
- `test_fix_p6a_a_marker_in_the_leg_root_is_not_evidence`,
- `test_fix_p6b_an_unrecognised_file_is_listed_not_copied_and_the_harvest_succeeds` (3 params),
- `test_fix_p6b_a_row_reference_to_an_unrecognised_file_is_listed_and_not_refused`,
- `test_fix_p6b_the_a3_leg_harvests_with_its_marker_and_a_second_unknown_file`,
- `test_inv_the_marker_rule_does_not_loosen_the_other_grade_outputs`.

**B. The H5 committed-harvest window (8 tests, not anticipated by the brief).** `s29_support.make_a3` builds the a3 situation
in two steps:
1. A first run harvests `tg2…off-pilot.a1` through the fake ops. That fake ops (`b2_frozen_add_support.SeqOps.harvest`) writes a
   self-hashed `HARVEST.json` with state VALID at `harvest_path(<attempt>)/HARVEST.json`.
2. The fixture then marks the leg "not harvested" only by removing the `harvested` entry from `sequence.json`.

Under v1.1 H5 ("so is a leg whose harvest is already committed (its published `HARVEST.json` exists), even when `sequence.json`
does not show it"), this is exactly the window that must be left as recorded. Item 2 therefore leaves it INVALID. These tests
fail:
- `test_fix_h5_the_resumed_run_rederives_the_state_harvests_and_goes_on_to_the_next_leg`,
- `test_new_h5_the_rederived_record_has_the_new_state_the_host_changes_and_the_supersession_and_verifies`,
- `test_new_h5_the_original_sealed_leg_json_is_kept_byte_identical_and_is_harvestable`,
- `test_new_h5_every_consumer_sees_the_new_state`,
- `test_inv_h5_the_run_baseline_is_not_rewritten`,
- `test_inv_h5_a_second_resume_finds_the_leg_done_and_changes_nothing`,
- `test_fix_h5_when_the_recorded_chain_is_not_clean_the_leg_stays_invalid_with_classify_legs_reason`,
- `test_fix_h5_the_recorded_overrun_flag_gives_the_overrun_state_when_the_chain_is_not_clean`.

Evidence that this is the only cause:
- All 8 logs contain `INVALID by the host change and its harvest is already committed; left as recorded`.
- With the item-2 check temporarily disabled (`if False and …`), all 12 tests of `test_s29_h5_rederive.py` passed. The check
  was then restored (verified: no `False and` left in the file) and the whole suite above ran on the restored code.

The fixture needs fixing, not the code: the a3 shape requires the attempt's `HARVEST.json` to be absent (the a3's harvest was
refused, so nothing was published). For example, `make_a3` could delete
`r1["ops"].harvest_path(f"{OFF_PILOT}.a1") / "HARVEST.json"` when `harvested=False`.

I did not narrow the check (for example to "a verified `HARVEST.json` naming another state") to make these tests pass. That
would satisfy the tests rather than the spec, and it would weaken a fail-closed rule.

## Notes for the reviewer

- Candidate 1's `HARVEST.json` format carried `sha256` in `unrecognised[]` and `unrecognised_references[]`. I did not check
  whether any harvest ran with candidate 1 outside this copy. If one did, its record lists digests of unscanned bytes.
- The kept-original temp file is `.leg.c360.json.tmp` in the leg root. If a crash leaves it behind and the leg is harvested
  before a resume removes it, the harvest lists it as unrecognised (P6b) and does not refuse.
- `_check_supersession` runs only when `leg.json` has a `c384` key. A `leg.c360.json` beside a `leg.json` without one is
  harvested and self-hash-checked as before.

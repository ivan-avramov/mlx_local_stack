# Implementer report — S29 record-not-block (candidate 1)

Baseline `204a8da16ac301c8a98cceec69a9a8af91d3b12d`. Spec `docs/specs/s29-record-not-block.md` v1.0. Nothing committed.

## Mechanisms chosen (where the spec left them free)

- **H1** `Sequencer.host_at_launch`: before a launch the live fingerprint is diffed against `<out-base>/host_env.json`;
  a non-empty diff is logged (`host environment differs from the baseline before <leg>: …`) and recorded on the leg's
  sequence entry (`host_env_before`, only when non-empty, so entries without a change keep their old shape). The leg launches.
- **H2** the fingerprint taken at launch is diffed against the one at the leg's end. `leg.json` carries
  `host_env_before` (vs the run baseline at launch) and `host_env_during` (launch → end), both lists, whenever the
  `host_env` seam exists (fakes without it: `leg.json` unchanged). `state` / `reason` / `class` come only from
  `classify_leg` + the existing OVERRUN rule. A during-diff is logged and also put on the sequence entry (`host_env_during`).
- **H3** `host_env_start` (resume) and the exception log record into `sequence.json` `host_env_events`
  (`{at, where, changes}`) and log; `host_env_final` records `host_env_after_last_leg` (as before, before publication) and logs;
  none stops. `after_leg` has no host stop. `host_refusal` is removed. **Kept**: an unreadable / unsealed / tampered
  baseline still stops (rc 1) — that is the run's own record failing to verify, not a host change (spec: sealed records stay
  verifiable; the existing s26 tests for it are unchanged and pass).
- **H4** `cmd_positives` records `host_env_changes` (the diff of `host_env` → `host_env_after`) in the sealed record and prints
  it; nothing is appended to `problems`.
- **H5** `Sequencer.c384_supersede`, called in `process()` for the latest entry when `--rerun` is not given for that leg.
  It acts only when the sequence entry and the self-hash-verified `leg.json` are INVALID with a reason starting
  `host environment changed during the leg: `, no ` (prior: `, and the attempt is not harvested. It then:
  1. derives `classify_leg(root, recorded chain_rc, arm)` (+ OVERRUN when the recorded `overrun` is true and the chain did
     not finish cleanly);
  2. writes the original `leg.json` bytes exclusively to `leg.c360.json` (byte-identical; if it already exists it must hash to
     the original, else Stop rc 1);
  3. atomically replaces `leg.json` with a sealed record: the original's fields, the new `state` / `reason` / `class`,
     `host_env_before: []`, `host_env_during` (the C360 reason's diff list) and a `c384` block (`rule`, `superseded`
     (file name), `superseded_sha256` (the original's self-hash), `superseded_file_sha256` (its bytes), `superseded_state`,
     `superseded_class`, `superseded_reason`, `host_env_before_basis`, `at`);
  4. updates the sequence entry (state, reason, `host_env_during`, `c384`), logs one line.
  A prior reason or an already harvested attempt is logged and left as recorded (it then stops as any INVALID latest leg
  does). Crash windows are covered: kept file written but `leg.json` not replaced → redone; `leg.json` replaced but
  `sequence.json` not saved → the entry is synced from the superseding record (after checking `leg.c360.json`).
  **Why replace `leg.json` rather than add a side record:** every consumer the spec names (sequencer, harvest,
  `p426_freeze.read_leg`, `p426_signals`, `p426_verify`) already reads `leg.json` and verifies its self-hash; making
  `leg.json` the superseding sealed record means all of them show the new state with **no change** to `p426_freeze.py`,
  `p426_signals.py` or `p426_verify.py` (none was touched). The original survives byte-identical as `leg.c360.json`,
  which the harvest publishes to `main` beside it (rule `LEG_MAIN`) and self-hash-checks as an immutable record. If the
  operator reads "kept" as "kept at the path `leg.json`", this is the point to push back on (see "Open" below).
- **P6a** `.marker` added to `TG2_GRADE_SUFFIXES`: only directly in `<lang>__<item>.grades/seq-NNNN/` (tg2 languages), evidence,
  scrubbed and gated like the other grade outputs. Anywhere else a `.marker` still has no rule.
- **P6b** `_inventory` puts a regular file with no rule into an `Unrecognised` collector instead of `problems`; it is never
  staged. `_ref` lists a `$STACK_WORKDIR` reference that resolves to such a file in `unrecognised.refs` (with the recorded
  digest and whether it matches) instead of the "referenced file … is missing" refusal. `HARVEST.json` gains
  `unrecognised` (`[{source, size, sha256}]`, portable typed source names) and `unrecognised_references`
  (`[{reference, source, sha256, sha256_matches}]`), both self-hashed with the record and gate-checked like it. The CLI prints
  one `UNRECOGNISED: …` stderr line per file / reference; `BoxSeqOps.harvest` returns them as `notes` and the sequencer logs
  them. Every other refusal is unchanged (symlinks, non-regular files, scrub / PII / secrets, self-hash, missing `leg.json`,
  state checks, references outside the roots, missing chain-referenced leg files).

## Files

Added
- `benchmark/bench/tests/test_s29_impl_sequencer.py` — H1, H2 (+ classifier INVALID kept, no-seam unchanged), H3 (resume,
  final on both exits, exception, rehearsal, baseline still stops), H5 (a3 shape re-derived VALID + harvested + run continues,
  second resume idempotent, both crash windows, foreign `leg.c360.json` stops, prior left, harvested left, `--rerun` not
  superseded, classifier INVALID kept, OVERRUN rule, harvest rule for the kept file, reason split).
- `benchmark/bench/tests/test_s29_impl_harvest.py` — P6a (rule boundary, a3 grade dir with `execute.marker` / `execute.out` /
  `execute-readback.*` all row-referenced, scrub, credential still refuses), P6b (file + row reference listed and not copied,
  every root, digest mismatch listed, CLI log line, links / fifos still refuse, outside-roots still refuses, dry run), H5 (kept
  original harvested to `main`, tampered kept original refuses).
- `benchmark/bench/tests/test_s29_impl_positives.py` — H4.

Changed (code)
- `benchmark/bench/p426_wave2.py` — H1–H5 as above; positives H4; `BoxSeqOps.harvest` returns `notes`; `Sequencer.harvest`
  logs them.
- `benchmark/bench/p426_harvest.py` — P6a rule, `leg.c360.json` rule + immutability, P6b collector / reference listing /
  `HARVEST.json` fields / CLI log lines, module docstring.

Not changed: `p426_freeze.py`, `p426_signals.py`, `p426_verify.py` (not needed, see H5), `host_env.py`, `classify_leg`, the
scrub, tg1 paths, `bench/tests/s29_frozen/` (does not exist in this copy).

## Existing tests changed (all pin the old C360 refusal / INVALID / stop, or the harvest's no-rule refusal)

Each changed test carries a docstring / comment line `S29 … (C384): changed …`.

`benchmark/bench/tests/test_s26_impl_sequencer.py`
- `test_a_change_between_legs_refuses_the_next_launch` — pinned the pre-launch refusal; now: logged, recorded, all legs launch.
- `test_a_change_during_a_leg_makes_it_invalid_systemic_harvested_and_stops` — pinned host INVALID + stop; now VALID (classifier),
  `host_env_during` recorded, run goes on.
- `test_the_prior_reason_is_kept` — pinned the host reason with `(prior: …)`; now the classifier's reason, change recorded beside.
- `test_a_resumed_run_on_a_changed_host_refuses_until_the_host_equals_the_baseline` — pinned the resume refusal; now the rerun
  launches on the changed host (the leg is made INVALID by a classifier scenario so a rerun applies).
- `test_the_end_of_run_check_runs_before_the_run_files_are_published` (2 params) — pinned the end-of-run stop; now recorded
  before publication, rc 0, DONE / "stopping as asked".
- `test_a_host_change_stops_even_a_leg_whose_invalid_state_is_expected` — pinned the after_leg host stop; now R3 launches.
- `test_the_invalid_leg_stop_is_a_flat_fail_closed_statement` — pinned the wording of a stop that no longer exists; now no host
  STOP line, a log line instead.

`benchmark/bench/tests/test_s26_impl_positives.py`
- `test_a_host_change_during_the_positives_is_a_fail` — pinned host change → FAIL; now PASS with `host_env_changes`.

`benchmark/bench/tests/s26_frozen/test_s26_positives.py`
- `test_fix_a_host_change_anywhere_in_the_leg_fails_the_record` (3 params), `test_fix_each_host_change_is_its_own_problem`,
  `test_fix_an_exception_and_a_host_change_are_both_recorded` — pinned host changes as problems; now recorded in
  `host_env_changes`, not problems (the exception stays a problem).

`benchmark/bench/tests/s26_frozen/test_s26_round2.py`
- `test_fix_the_host_invalid_leg_stop_is_a_flat_fail_closed_statement`, `test_fix_the_other_guard_stops_carry_no_operator_wording`
  — pinned the wording of the three host stops; those stops no longer exist: rc 0, no STOP line, the log lines present.

`benchmark/bench/tests/s26_frozen/test_s26_sequencer.py`
- `test_fix_a_host_change_between_legs_refuses_the_next_launch`, `test_fix_a_resumed_run_on_a_changed_host_stops_before_launching`,
  `test_fix_a_leg_that_changed_the_host_is_invalid_systemic_with_the_diff_as_reason`, `test_fix_several_changes_are_joined_with_semicolons`,
  `test_fix_a_prior_reason_is_kept_in_parentheses`, `test_fix_a_settled_dnf_leg_is_not_spared`,
  `test_fix_a_rerun_after_an_invalid_host_leg_refuses_until_the_host_equals_the_baseline`,
  `test_fix_a_change_after_the_last_leg_is_caught_before_the_run_files_are_published`,
  `test_fix_a_change_after_the_through_leg_is_caught_on_the_through_exit` — each pinned a C360 refusal / INVALID / stop; each now
  asserts the C384 record (log line, `host_env_before` / `host_env_during` / `host_env_events` / `host_env_after_last_leg`) and
  that the run continues with the classifier's state.
- `test_fix_the_kv_lever_sequencer_guards_the_host_too` — pinned the kv resume refusal; now asserts the resume logs + records the
  change and proceeds to the launch checks, where this frozen base's minimal kv v8 (no worktree keys) raises
  `KeyError('n16_worktree')` — asserted explicitly with `pytest.raises` (the docstring already says the frozen base lacks kv
  records for the post-check path).

Harvest tests that used an unmatched file (outside the brief's named list; found by running every test module that imports the
two changed modules):
- `test_b2_s9_harvest.py`: `test_an_unmatched_file_fails_the_harvest_and_names_it`, `test_an_unmatched_file_in_a_named_run_directory_fails_too`,
  `test_a_final_tree_under_the_leg_root_follows_the_same_rule` — pinned the no-rule refusal; now the file is listed in
  `unrecognised` and not copied. `test_a_harvest_error_prints_one_refused_line_exits_2_and_publishes_nothing` — used an unmatched
  file only as a refusal trigger; trigger changed to a symlink (still refused), assertion unchanged.
- `test_b2_frozen_s9_harvest.py`: `test_new_an_unmatched_file_fails_the_harvest` — now rc 0, `UNRECOGNISED:` logged, listed,
  not copied.
- `test_p586_impl_harvest.py`: `test_dry_run_reports_every_problem_and_writes_nothing`,
  `test_dry_run_collects_scrub_and_secret_problems_with_inventory_ones`, `test_cli_dry_run_exit_codes` — used unmatched files as
  the inventory problems of a dry run; changed to symlinks at the same paths (still problems); assertions unchanged.
- `p586_frozen/test_p586_harvest.py`: helper `_problem_world` (feeds `test_dry_run_reports_every_problem_at_once_and_writes_nothing`,
  `test_cli_dry_run_prints_every_problem_and_exits_4`, `test_cli_without_dry_run_is_unchanged`) — same change, same reason.

## Commands and results

All via `../fe_test.sh stack <args>` from the copy root.

1. New tests on the unmodified baseline code (tests-first):
   `bench/tests/test_s29_impl_sequencer.py bench/tests/test_s29_impl_harvest.py bench/tests/test_s29_impl_positives.py`
   → 31 failed (every H1–H5 / P6a / P6b / H4 scenario); the rest (kept refusals, baseline still stops, rerun) passed.
2. Same three after implementation → all pass (one of my own tests had a bug — a "tamper" that changed nothing — fixed).
3. Named modules + new tests (final run, see counts below):
   `bench/tests/test_s29_impl_sequencer.py bench/tests/test_s29_impl_harvest.py bench/tests/test_s29_impl_positives.py
   bench/tests/test_s26_impl_sequencer.py bench/tests/test_s26_impl_positives.py bench/tests/s26_frozen
   bench/tests/test_p426_harvest.py bench/tests/test_s27_impl_harvest.py bench/tests/test_m76_b4b1_impl_wave2.py
   bench/tests/test_m76_b4b1_fe_wave2.py bench/tests/test_m76_b4b2_impl_verify.py bench/tests/test_m76_b4b2_impl_signals.py`
   → first full run: **477 passed, 1 failed** (the pre-existing failure below). Final run after the last edits (a function
   moved, one test assertion tidied), the same list plus `test_b2_s9_harvest.py test_b2_frozen_s9_harvest.py
   test_p586_impl_harvest.py p586_frozen test_b2_s8_wave2.py`: **979 passed, 1 failed** (the same pre-existing failure).
4. Every other test module importing `p426_wave2` / `p426_harvest` (44 modules + `p586_frozen/` + `p613/`, listed in the
   command history; not the whole suite) → **2188 passed, 2 skipped** (after the harvest test changes above; before them 11
   failed, the ones listed).

## Pre-existing failure (not caused by this change)

`s26_frozen/test_s26_positives.py::test_fix_an_exception_message_never_carries_the_absolute_home_path` fails in this harness
**on the baseline too**: verified by temporarily restoring the baseline `p426_wave2.py` (candidate saved to scratch, then put
back and `cmp`-verified) → `1 failed`. Cause: this harness's TMPDIR is under the home directory, so the fake host world's
`bin_dirs` paths inside `host_env` / `host_env_after` (recorded on the baseline already) contain the home path. On a box whose
TMPDIR is outside home it passes. Not changed.

## What I could not satisfy / open points for the reviewer

- **"kept byte-identical" vs "kept at `leg.json`".** I keep the original's bytes as `leg.c360.json` and make `leg.json` the
  superseding sealed record (reasons above). If the designer wants the original to stay at the path `leg.json`, every consumer
  (`p426_freeze.read_leg`, `p426_signals`, `p426_verify`, the harvest's state read, the sequencer) would need to prefer a
  side record — a wider, riskier change I chose not to make.
- **H5 `host_env_before` for the a3 leg is `[]` by inference**: the C360 sequencer refused any launch that differed from the
  baseline, so the recorded fact is "no difference at launch"; the record says so (`c384.host_env_before_basis`). The real a3
  launch fingerprint was never stored.
- **`host_env_during` for the a3 leg is the C360 reason split on `"; "`** (the reason is the `"; "`-join of `diff()`); a change
  string containing `"; "` would split wrongly — `diff()` never emits one for the fingerprint sections it has. The verbatim
  reason is kept as `c384.superseded_reason`.
- An unreadable / tampered run baseline still stops. I read it as a record-integrity failure, not a host change; flag it if
  C384 is meant to cover it too.
- `need()` references from `chain.json` to leg-root files that have no rule still refuse as "missing" (only `$STACK_WORKDIR`
  artifact references go through `_ref`); those are always session `.jsonl` / `.manifest.json`, which have rules.
- The real a3 leg root was not available to run against (only its `leg.json`, `sequence.json` and the grade listing); the
  tests rebuild its shape.

## Candidate

`git add -A -- benchmark && git diff --cached 204a8da16ac301c8a98cceec69a9a8af91d3b12d -- benchmark > …/out/candidate-1.diff`
→ **1691 lines** (14 files: 2 code, 9 existing tests changed, 3 new test files). Staged only, not committed.
Note: the extra-importer run (item 4) ran before the final cosmetic edit in `p426_wave2.py` (a function moved, no behaviour
change); it was not repeated in full.

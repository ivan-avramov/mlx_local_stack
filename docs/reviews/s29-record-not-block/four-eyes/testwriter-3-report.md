# Test-writer report, delivery 3 — frozen tests amended to spec v1.1

Files touched, all under `benchmark/bench/tests/s29_frozen/`: `test_s29_harvest.py`, `test_s29_oracles.py`, `s29_support.py` (amended), `test_s29_v11.py` (new).
Nothing else edited; nothing committed. The candidate is applied in this copy (`git status` verified before and after the baseline run).

## Amended (what v1.1 changes, nothing more)

| what | change | why |
|---|---|---|
| `test_s29_harvest.py::listing()` (oracle helper) | a listing record now needs the file's **size**, no value equal to the sha256 of the file's bytes, and (`digest_free=True`, default) that digest nowhere in `HARVEST.json`. `digest_free=False` for the two tests whose row legitimately records a digest | v1.1 P6b: scrubbed path + size, nothing derived from unscanned bytes |
| every test using `listing` (`…evidence_only_directly_in_a_grade_seq_dir` ×7, `…marker_in_the_leg_root…`, `…unrecognised_file_is_listed…` ×3, `…marker_rule_does_not_loosen…`) | unchanged text; they now inherit the no-digest rule | same |
| `…row_reference…` and `…a3_leg_harvests_with_its_marker_and_a_second_unknown_file` | `digest_free=False` (the row's own recorded digest is a recorded fact, not derived from the file) | v1.1: reference keeps the digest-match boolean |
| module docstring / assertion message | wording: path + size, no digest | v1.1 |
| `test_s29_oracles.py` listing oracle test | the listed record has no digest; a record that carries the digest of the bytes is now rejected by the oracle (known negative) | v1.1 |
| `s29_support.make_a3` | new `committed_harvest=False`; by default the HARVEST.json the first run's fake harvest published for the attempt is removed | v1.1 H5: a committed harvest is left as recorded. Without this the a3 fixture (a harvest that was REFUSED) would have contradicted v1.1 — a fixture bug exposed by the amended spec, not a candidate property |

Kept as the spec still supports: all P6a tests, the account-name test (it is now also required by v1.1 "never refusing"), every refusal-stays test, every H1–H4 test.

## Added: `test_s29_v11.py` (15 test cases)

| test | class | why |
|---|---|---|
| `test_fix_h5_a_leg_whose_harvest_is_published_but_not_recorded_is_left_as_recorded` | FIX | v1.1 committed-harvest window: published `HARVEST.json`, no `harvested` entry → not re-derived; every file byte-identical; rc 1; stop on the leg |
| `test_inv_h5_without_a_published_harvest_the_same_leg_is_rederived` | INV | control for the above (same state, harvest absent → VALID) |
| `test_new_h5_the_kept_original_is_installed_by_rename_and_a_failed_install_changes_nothing` | NEW | atomic kept original: observed as a rename/link of a complete file onto the kept path; failure injected there leaves `leg.json` unreplaced and entry INVALID; next resume completes, kept bytes identical. **Mechanism assumption:** atomic = rename/link (the test fails if no rename/link is used) |
| `test_new_harvest_publishes_a_c384_leg_json_with_its_kept_original` | NEW | control: grafted C384 `leg.json` (from the sequencer's own H5 flow, leg/attempt rewritten and resealed) + kept original harvests; kept original published |
| `test_new_harvest_refuses_a_c384_leg_json_whose_kept_original_is_missing_differs_or_is_a_link[missing, differs, symlink]` | NEW | harvest supersession-link check; nothing published |
| `test_fix_h3b_a_clean_final_check_after_a_changed_one_leaves_an_empty_final_diff` | FIX | run 1 clean → host changed, run 2 ends changed → host reverted, run 3 ends clean: `host_env_after_last_leg == []` in `sequence.json` and in the last published copy. **Assumption:** the field name `host_env_after_last_leg` (existing since C360) |
| `test_fix_p6b_a_reference_with_a_wrong_recorded_digest_is_listed_with_a_false_match_and_not_refused` / `…right_digest… true_match` | FIX | v1.1 match boolean (record naming referencing + referenced file holds `False` / `True`) |
| `test_fix_p6b_a_reference_from_a_manifest_to_an_unrecognised_file_is_listed_and_not_refused` | FIX | "from any harvested record" (probe manifest, not a row) |
| `test_fix_p6b_a_path_the_scrub_would_change_is_listed_scrubbed_and_never_refuses[leg, evidence, run]` | FIX | account-named directory in each root: harvest succeeds, listing has file name and size, not the account name |
| `test_fix_p6b_the_listing_has_no_digest_of_the_files_bytes` | FIX | no sha256 (full or 16-char prefix) of the bytes anywhere in `HARVEST.json`; size present |

## Outcomes (as they are)

Command: `../fe_test.sh stack bench/tests/s29_frozen --tb=no -rA`

| | baseline | candidate 1 |
|---|---|---|
| summary line, verbatim | `67 failed, 20 passed in 11.00s` | `24 failed, 63 passed in 74.80s (0:01:14)` |

(87 tests: 72 earlier + 15 new.)

**Baseline:** the 20 passes are the invariants (refusals that stay, unchanged-host controls, oracles, plain-leg control). All 15 new cases fail on the baseline (the `test_inv_h5_without_a_published_harvest…` and the three harvest-link tests that are positive controls fail there too: no H5 flow / no marker rule on the baseline; so those controls say nothing on the baseline).

**Candidate 1 (written for spec v1.0): 24 failures, all on v1.1 behaviour:**
- 15 × no digest in the listing (the candidate lists `sha256`): `…evidence_only_directly_in_a_grade_seq_dir` ×7, `…marker_in_the_leg_root_is_not_evidence`, `…unrecognised_file_is_listed_not_copied…` ×3, `…row_reference…`, `…a3_leg_harvests_with_its_marker_and_a_second_unknown_file`, `…marker_rule_does_not_loosen…`, `…listing_has_no_digest_of_the_files_bytes`
- 4 × a scrubbed path refuses the harvest: `…account_is_scrubbed_in_the_listing`, `…path_the_scrub_would_change…` ×3
- 5 × new v1.1 behaviour absent: committed-harvest window 1, kept original not installed by rename 1, link check (`missing`, `differs`) 2, H3b stale final diff 1
(15 + 4 + 5 = 24; the failing tests per name are in the `-rA` output.)

**Candidate 1 passes (v1.1 controls and what it already did):** the H5 committed-harvest control, the grafted-C384 positive control, the `symlink` link case (refused by the existing symlink rule, not by a link check), the match booleans `true` / `false`, the manifest reference, all H1–H4, all P6a, all refusal-stays tests, all H5 re-derivation tests (the amended `make_a3` did not change them).

Cautions: (1) the link-check tests graft a `leg.json` from the candidate's own H5 flow; against a v1.1 implementation the grafted block carries whatever that implementation writes, which is what the check should read. (2) The atomic-install test is the most mechanism-bound new test (rename/link); if the implementer installs atomically some other way (e.g. `O_TMPFILE` + `linkat`), it will need review. (3) H3b pins the field name `host_env_after_last_leg`.

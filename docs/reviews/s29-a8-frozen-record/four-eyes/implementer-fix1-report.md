# Implementer report — fix round 1 (F1), S29 B8-A8 rule 3.6

Baseline `a073d594e`. Candidate 1 (staged) kept as is; production code unchanged in this round. Only two test modules changed:
`benchmark/bench/tests/test_m76_b4b2_fe_real.py` and `benchmark/bench/tests/test_m76_b4b2_impl_golden.py`. Export:
`out/candidate-2.diff`. Nothing committed.

How the new expectations were found (no A8 value read): a scratch-only probe (`impl/scratch/fix1_driver/test_struct.py`, not in
the candidate) recorded only statuses, counts, key paths and member names. It found two things. (1) The real B8-A8 record has all
four pairs accepted, the record complete, both re-checks `ok` and latency `present`. (2) With B8-A8, the sheet outside the A8
section differs in exactly three places: the panel completeness `expected`/`missing_members` (+ `A8-s1`, `A8-s2`), the
`panel_incomplete` flag (items/text, same members), and four `- A8 …` lines in the Decode section (markdown only; the JSON keeps
A8 decode under `decode.A8`). The A8 lines' content was redacted in the probe output.

## Tests changed (old → new; the intent kept)

### `test_m76_b4b2_fe_real.py`
1. **Renamed** `test_the_real_pilot_pair_builds_with_the_pilot_accepted` → `test_the_real_pilot_and_decider_pairs_build_accepted`.
   - Old: pilot accepted, reasons `[]`, diagnostic; s1/s2/reload `incomplete` with reasons; record `incomplete`.
   - New: pilot unchanged. s1/s2 (`pair`) and reload (`diagnostic`) are `accepted` with reasons `[]` and keys present. Record
     `complete`, corpus tg2, sessions `[s1, s2]`.
   - Intent: the real pilot pair builds accepted, and B8-A8 builds over the real harvested sessions.
2. **Renamed** `test_the_real_s1_is_incomplete_with_x_s1_unaccepted` → `test_the_real_decider_pairs_are_accepted_on_the_amendment`.
   - Old: s1 `incomplete`, no keys; s2/reload `incomplete`; premise X s1 attempt 2 `INVALID`.
   - New: the amendment binds this v8 base (`v8_base_sha256`) and the accepted pilot's dossier (its file sha); amendment and v8
     base are both hashed `inputs`. Each selected decider attempt (s1, s2, reload × both arms) has `tg2_leg` = session and
     `frozen_record.sha256` = the amendment's sha. The pilot attempts name the v8 base sha. s1/s2/reload are accepted with no
     reason. The premise is kept: X s1 a2 is still `INVALID`, and neither a1 nor a2 is the selected X s1 attempt.
   - Intent: the INVALID X s1 attempts never feed A8. The test now also pins rule 3.6 via the amendment on the real records.
3. **Renamed** `test_the_real_latency_is_incomplete` → `test_the_real_latency_is_present_and_verifies`.
   - Old: `exec_latency.json` absent; latency `incomplete`.
   - New: latency `present` with path `wave2.tg2/run/exec_latency.json`. Its sha256 equals the published record's seal, the row
     count matches the file (> 0), and the file is a B8-A8 input bound to its byte sha.
   - Intent: latency is read from the sealed published record and stays descriptive. Row values are not asserted.
4. **Kept name** `test_a8_record_changes_only_the_a8_parts_of_the_real_sheet` (both cases, `SIGNALS.json-False` and
   `SIGNALS-partial.json-True`).
   - Old: `projection(got) == projection(want)`; `not A8.verdict` ("only the pilot exists"); old flags ⊆ new flags.
   - New: `projection` also removes `A8-*` names from `panel.completeness.expected` / `missing_members`, then requires equality.
     The test asserts B8-A8's panel members are `["A8-s1", "A8-s2"]`. Got `expected` = committed `expected` + those members, and
     got `missing_members` = committed + those not in the frozen panel. Flags must be equal once A8 is removed
     (`flags_without_a8`: drops `member == "A8"` flags and takes the A8 members out of `panel_incomplete` items/text).
   - The `verdict` assertion was removed. The test does not read or assert any A8 verdict, and it does not assert whether any
     A8 flag exists.
   - Intent: B8-A8 changes the sheet only in A8 content. This is now stricter on flags (equality instead of subset, after the
     A8 parts are removed).
5. Module docstring: "decider absent" → pilot pair and decider; decider legs run on the S29 amendment.

### `test_m76_b4b2_impl_golden.py`
6. **Renamed** `test_pilot_pair_b8_a8_shape` → `test_real_b8_a8_shape_with_the_decider`.
   - Old: record `incomplete`; pilot accepted; s1/s2/reload `incomplete`; pilot 4 keys with no null sha; latency `incomplete`;
     re-checks `incomplete`; pilot `tampered` empty for both arms.
   - New: record `complete`. All four pairs are accepted with reasons `[]`, and every pair has keys with no null manifest sha.
     The pilot has 4 keys, the amendment is an input, latency is `present`, and both re-checks are `ok` (sealed record verified;
     the label stays descriptive). The pilot `tampered` check is unchanged.
   - Intent: the shape check now runs on the real complete record.
7. **Renamed** `test_with_b8_a8_the_sheet_differs_only_in_the_a8_section` → `test_with_b8_a8_the_sheet_differs_only_in_a8_content`.
   - Old: the markdown with the A8 section and the B8-A8 header line removed equals `SIGNALS.md` byte for byte. In the JSON,
     A1/A5/A7/A2/A3/A4/M1 equal the committed ones, and `panel` and `flags` are equal. A8 status `incomplete…`.
   - New, markdown: also removed are the `- A8…` lines in the Decode and Flags sections (A8 decode / A8 flags). The rest must
     equal `SIGNALS.md` with only the panel-completeness line and the `panel incomplete` flag line rewritten to the new
     expected/missing lists.
   - New, JSON: the added expected members are exactly `["A8-s1", "A8-s2"]`, appended after the committed list. The axes are
     unchanged. `panel` equals the committed one once the A8 members are removed. Non-A8 flags equal the committed ones once
     the A8 members are removed. The A8 section status is not `incomplete…`: the decider feeds it. This is a completeness check
     only; no verdict is read.
   - Intent: adding B8-A8 changes the sheet only in A8 content.
8. Module docstring updated to match.

No production code changed. No test showed a defect.

## Commands and results
All run from the copy via `../fe_test.sh stack …`.
1. Scratch probe (`impl/scratch/fix1_driver/test_struct.py`): 2 passed (structure only).
2. `bench/tests/test_m76_b4b2_fe_real.py bench/tests/test_m76_b4b2_impl_golden.py -q`: **30 passed**, 0 skipped (the prompt-check
   tests ran).
3. Full run: `bench/tests/s29b_frozen`, `bench/tests/test_s29_impl_a8_frozen_record.py` and every module in `REALREC_TESTS`
   (`-q -rs`): **1595 passed, 2 failed, 0 skipped**, exit 1 (count taken from the progress markers; the runner printed no summary
   line). Every one of the seven F1 tests passes, and so does every `REALREC_TESTS` module and `test_s29_impl_a8_frozen_record.py`.
   The two failures are in the read-only frozen suite:
   - `s29b_frozen/test_a8_frozen_record.py::test_r2_pilot_attempt_naming_the_amendment[n16]`
   - `s29b_frozen/test_a8_frozen_record.py::test_r2_pilot_attempt_naming_the_amendment[x]`

   Both fail at line 265 (`assert all(got[s]["accepted"] is True for s in DECIDER)  # the deciders are untouched`). The pilot
   rejection on line 264 holds. This round changed tests only, so the same failures come from candidate 1's production code.

## Finding D1 — the frozen tests show a defect in candidate 1 (reported, not fixed, per the brief)

| Finding | Recommendation |
|---|---|
| In `verify_a8_kv`, `pilot_dossier_sha256` is set only when B8-A8 accepts the pilot pair. If the pilot is rejected for any reason (here: one pilot chain names the amendment), the value is `None`. `a8_amendment_problems` then reports "B8-A8 accepted no pilot pair whose dossier the amendment could name", and s1/s2/reload are all rejected. The frozen test requires a rejected pilot to leave the deciders untouched. | Bind the amendment to the dossier of the pilot pair recorded in `sequence.json`, using the file's byte sha read through the `Reader`, whether or not B8-A8 accepts the pilot. Fail closed only when that record or dossier is missing, or when its sha differs from `amendment.pilot_dossier_sha256`. That matches the goal ("provably extends … this campaign's accepted pilot", accepted by the runner) and keeps `test_r2_amendment_dossier_must_be_the_accepted_pilots`. Strongest counterpoint: spec R1 says literally "the pilot pair B8-A8 accepted", and candidate 1 follows that wording. Candidate 1's own test for "no accepted pilot → deciders rejected" (`test_s29_impl_a8_frozen_record.py`) encodes it and would need to change. The designer should decide which reading is meant. |

## Judgement calls
- J2. The A8 flag and decode lines are tolerated (dropped from the comparison), not asserted present or absent: whether they
  exist depends on the A8 verdict. The test does pin that every other flag and line is unchanged.
- J3. Re-check status `ok` is asserted in the golden shape test. It only says the sealed re-check record verified; its
  `inside` / `operator_review` values are not read.

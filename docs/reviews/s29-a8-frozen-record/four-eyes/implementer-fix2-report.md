# Implementer report — fix round 2 (D1), S29 B8-A8 rule 3.6, spec v1.1 R1

Baseline `a073d594e`. Started from candidate 2, already staged. This round fixes D1 only. Export: `out/candidate-3.diff`.
Nothing was committed. The frozen suite `s29b_frozen/` and the spec were not touched.

## Production change (`benchmark/bench/p426_verify.py`)
- New `a8_recorded_pilot_dossier_sha256(reader, seq, ref, test)` → `(sha, None)` or `(None, why)`.
  - It picks the pilot pair record from `sequence.json` with the same latest-attempt selection B8-A8 uses
    (`_sequence_pair_and_superseded`). Its `RefusalError` (no record, or an ambiguous one) becomes a reason, not a refusal.
  - It resolves the dossier path the same way `_a8_session` does: the `dossier` field, else the default name. The path must sit
    under `pairs/`, with no `..`, no symlink, and nothing resolving outside `pairs/`.
  - It reads the file through `reader.try_read_bytes`, so the file is a hashed input. A missing file gives `(None, "… is missing")`.
- In `verify_a8_kv`, the amendment is now bound to this sha whether or not B8-A8 accepts the pilot pair. The sha is computed once,
  before the session loop, and only when an amendment is published; otherwise the inputs set is unchanged from before.
  - Candidate 1's pilot-first ordering was reverted: the sessions run in the original order again. The code that took the sha
    from an accepted pilot record was removed.
- `a8_amendment_problems`, `a8_frozen_record_reasons`, `_a8_plan_reasons` and `_a8_session` each gained an optional
  `pilot_dossier_problem` and pass it on. With no sha, the specific reason (missing record, missing dossier or bad path) becomes
  the rule-3.6 reason on each decider attempt. A differing sha is still a reason; its wording now says "recorded pilot dossier".
- Nothing else changed: no other rules, no runner, sequencer, signals or panel code.

## Test changes (`benchmark/bench/tests/test_s29_impl_a8_frozen_record.py`)
- The module docstring now cites v1.1 R1.
- `test_r2_no_accepted_pilot` was renamed `test_r2_no_recorded_pilot_dossier`. It used to mean "no accepted pilot means the
  deciders are rejected"; now it means "no recorded pilot dossier sha is a rule-3.6 reason". It also checks that the specific
  problem text reaches the reason.
- New `test_e2e_rejected_pilot_leaves_the_deciders_accepted`: one pilot chain's `tg2_leg` is changed, so B8-A8 rejects the pilot.
  s1, s2 and reload stay `accepted` with `reasons == []`, and the pilot dossier is a hashed input with its byte sha.
- New `test_e2e_recorded_pilot_dossier_missing_or_wrong[missing|changed]`: the dossier file is deleted, or its bytes are changed
  so its sha differs from the amendment's. Every decider pair is then `rejected` with a rule-3.6 "pilot dossier" reason, and the
  record is `incomplete`.
- New `test_recorded_pilot_dossier_without_a_pilot_record`: given the real `sequence.json`, the function returns the dossier's
  byte sha. With the pilot record removed, it returns `None` with a reason, and does not crash.

No A8 result value was read or reported. The new tests check only status, reasons and input shas.

## Commands and results (all `../fe_test.sh stack …` from the copy)
1. `bench/tests/s29b_frozen bench/tests/test_s29_impl_a8_frozen_record.py`: **66 passed**, exit 0. This includes
   `test_r2_pilot_attempt_naming_the_amendment[n16|x]`, the two tests that failed in round 1, and
   `test_r2_amendment_dossier_must_be_the_accepted_pilots`.
2. Full set: `s29b_frozen`, `test_s29_impl_a8_frozen_record.py` and all 50 modules in `.realrec_tests`, with `-rs`.
   **1601 passed, 0 failed, 0 skipped** (summary line `1601 passed in 722.21s`), exit 0. Round 1 had 1595 passed + 2 failed =
   1597; the extra 4 are the new tests.

## Judgement calls
- J4. The recorded pilot dossier is read only when an amendment is published. Without one, no decider can pass through the
  amendment anyway, and skipping the read keeps the inputs set unchanged in that case.
- J5. "The pilot pair the sequencer recorded" is taken to be the record of the latest pilot attempts, using the same selection
  B8-A8 applies to the pilot session. If that selection is missing or ambiguous, the deciders get a reason, never a refusal.

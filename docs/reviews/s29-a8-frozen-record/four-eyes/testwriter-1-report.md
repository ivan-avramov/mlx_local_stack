# Test-writer report, delivery 1 — S29 B8-A8 rule 3.6

File: `benchmark/bench/tests/s29b_frozen/test_a8_frozen_record.py` (+ `__init__.py`), in the copy at baseline `a073d594e`.

## Run status — NOT RUN
`../fe_test.sh stack bench/tests/s29b_frozen` was refused by the sandbox ("requires approval") on two attempts, as were my
ad-hoc Python probes. **No test has been executed; no baseline outcome exists.** Summary line: none (nothing ran).
The "expected on baseline" column is my reading of `p426_verify.py` (`_a8_plan_reasons`, line ~2739), not an observation.
Run the command once and fill in the outcomes before handing to the implementer.

## Tests (class, expected on baseline — unverified)
| test | class | expected baseline |
|---|---|---|
| test_the_real_records_have_the_described_shape | invariant | pass |
| test_r1_decider_pair_on_the_amendment_is_accepted[s1,s2,reload] | fix | fail |
| test_r1_document_is_complete_when_the_deciders_are_on_the_amendment | fix | fail |
| test_r1_pilot_on_the_v8_base_is_accepted | invariant | pass |
| test_r2_no_amendment_published | new | pass (deciders already rejected; the assertion on `status` and pilot also hold) |
| test_r2_unsealed_amendment | new | pass (trivially) |
| test_r2_amendment_without_a_seal | new | pass (trivially) |
| test_r2_amendment_naming_another_v8_base | new | pass (trivially) |
| test_r2_amendment_naming_another_pilot_dossier | new | pass (trivially) |
| test_r2_amendment_without_a_binding_field[v8_base_sha256,pilot_dossier_sha256] | new | pass (trivially) |
| test_r2_decider_attempt_naming_a_foreign_sha[0*64,not-a-sha] | invariant | **fail** (asserts s2/reload accepted, which baseline rejects) |
| test_r2_decider_attempt_without_a_frozen_record | invariant | pass |
| test_r2_pilot_attempt_naming_the_amendment[n16,x] | new | **fail** (asserts the deciders stay accepted); guards against "accept either sha anywhere" |
| test_r2_pilot_attempt_naming_a_foreign_sha | invariant | pass |
| test_r2_amendment_dossier_must_be_the_accepted_pilots | new | pass (trivially) |
| test_r3_the_amendment_is_a_recorded_input | new | fail |
| test_r3_a_later_change_to_the_amendment_is_detected | new | fail (baseline never reads it) |
| test_r3_a_later_change_to_the_v8_base_is_detected | invariant | pass |
| test_r4_real_records_b8_a8_complete_all_pairs_accepted | fix | fail |
| test_r4_cli_writes_a_complete_b8_a8 | fix | fail |
| test_r4_b8_json_is_byte_identical | invariant | pass |
| test_r4_b8_json_does_not_include_a8 | invariant | pass |

Several R2 negatives pass trivially on the baseline because it rejects every decider; their value is after the fix, each is paired
with the R1 control (untampered copy accepted). The foreign-sha and pilot-names-amendment cases are the ones that discriminate.
Misclassifications possible (e.g. the foreign-sha test is labelled invariant but fails on baseline); relabel after the first run.

## Assumptions
- Pair record shape: `verify_a8_kv(results_root, base_b8_sha256)` returns `pairs[]` with `pair`, `accepted`, `status`, `reasons`,
  `attempts{arm: name}`; reasons for rule 3.6 contain the text `rule 3.6` and the attempt name (as today's `_a8_plan_reasons`).
- A tampered `chain.json` is not pinned by HARVEST (only `main`-destination files are), so edits there yield only rule-3.6 reasons;
  tests filter on those.
- Amendment recorded as an `inputs` key ending `wave2.tg2/run/amendment.json` (same style as `v8_base.json`).
- "Never a crash": a missing amendment returns a document (no exception).
- Not asserted (spec ambiguous): a decider attempt naming the v8 base sha (neither required nor excluded); a decider when the
  pilot pair itself is rejected; amendment `kind` / corpus validation.
- The worlds are hard-linked copies of the real 149 MB tree (copy fallback if linking fails); edits replace files.
- R4 relies on the real records on `main`; tests skip with a reason if `amendment.json`, `v8_base.json` or `B8.json` are absent.
- No A8 result, pass rate or verdict is read or asserted; only acceptance status and rejection reasons.

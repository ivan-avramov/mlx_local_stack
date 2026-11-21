# M76 B4b-2 — implementer fix round 1 report (change review r1 of 3; ledger `change-ledger-r1.md`, spec v1.5)

The working tree is candidate 1 (INDEX, baseline `26287dce2`) plus the edits below. Nothing was staged, committed, reset or pushed.

## 1. Headline

- **Red tests** (`benchmark/bench/tests/test_m76_b4b2_impl_r1fix.py`, 38 tests):
  - On candidate 1, 33 of the first 36 failed, and 6 of the 7 tests in the revised B5 set failed.
  - The tests that passed on candidate 1 are invariants: the conformed world is accepted, B3's own-run exemption, B10's real pilot seeds, and B5's "the runner's records stand".
  - On the fix, all 38 pass.
- **Frozen acceptance tests v2 (140): 35 FAIL on the fix.** Every one of them is a conflict between a frozen fixture and an adopted finding (B4, B10, B3, B2; §3).
  - With the B4-identity and B10-seed reasons neutralised (a temporary one-line edit, restored, and checked by grep that `TEMP-NEUTRALIZED` is absent), 138 of 140 pass. The 2 left are the B3 and B2 conflicts.
  - `test_m76_b4b2_fe_real.py`, which runs on the real harvested pilot pair, **passes** on the fix. The real records satisfy B2 (`load_slots`), B4 (v8 identity) and B10 (plan seeds).
- **Call forms:** both `verify_a8_kv(results_root)` and `verify_a8_kv(results_root, sha)` work (B1).

## 2. Per finding (change, red test, before → after)

Line numbers refer to the final working tree.

| id | change | red test(s) | before (cand. 1) → after |
|---|---|---|---|
| B1 | `p426_verify.py:2930` `verify_a8_kv(results_root, base_b8_sha256=None, draw_path=None)`: when None, it uses the sha of `<results_root>/B8.json` and refuses if the file is absent. An explicit value is the seam the CLI uses. | `test_b1_verify_a8_kv_takes_the_base_b8_from_the_results_root`, `test_b1_a_missing_b8_json_refuses` | TypeError ×2 → pass |
| B2 | `p426_verify.py:2435` `_a8_inventory` replaces `_a8_session_rows` / `_a8_harness_dnf` / `_a8_slots` and sits on `chain_rows.load_slots(check_unregistered=False)`. On top of that: an unregistered rows file that holds rows refuses (an empty one is tolerated); a slot from another session refuses; the harness-DNF sidecar must be sealed AND `== chain record`; a transport DNF beside a row or harness DNF refuses; the rule-9.3 "earlier attempts = range(k)" reason is kept. `_a8_load_attempt` is at `:2607`. | `test_b2_a_transport_dnf_record_beside_a_row_refuses`, `…rows_file_changed_after_validation_refuses`, `…chain_harness_dnf_record_differing_from_its_sidecar_refuses`, `…harness_dnf_without_a_reason_refuses` | 4 × DID NOT RAISE → pass |
| B3 | `p426_verify.py:2156` `discarded_runs(reader, att)` returns {(item, run)} for each `harness_fault` slot attempt. The run is the `run_id` in the provenance manifest of the invocation that attempt names, and it must also be in `seen_run_ids`. It is set on both loaders (`:2278` A7 and `_a8_load_attempt`). `final_tree_reasons` (`:2179`) exempts only `(rid, other) in discarded`. | `test_b3_another_seen_run_of_a_discarded_slot_is_an_orphan`; invariant `test_b3_the_discarded_attempts_own_run_is_not_an_orphan` | AssertionError [] → pass; invariant passed both times |
| B4 | `p426_verify.py:2657` `A8_V8_IDENTITY`. `a8_v8_pin_reasons` (`:2674`) checks v8 draw sha == `TG2_DRAW_SHA256` == the file read, and universe sha == `TG2_UNIVERSE_SHA256`; it is called once, `:2964`. `a8_v8_identity_reasons` (`:2689`) checks, per invocation manifest: probe code, scaffold policy, generation identity, draw / universe / image (`corpus_identity`) and `toolchain.grader_image_id` == v8; manifest and rows model == schedule pick. Called at `:2794`. Each mismatch is a REASON. | `test_b4_a_leg_not_carrying_the_v8_identity_is_rejected[×5]`, `test_b4_a_v8_whose_tg2_pins_are_not_the_committed_ones_is_rejected[×2]`, `test_b4_a_manifest_naming_another_model_is_rejected` | 8 × AssertionError [] → pass |
| B5 | `p426_verify.py:2540` `_a8_accounting`: requires exact agreement of slot state, ledger (`kind=row`, rerun index) and sidecar presence. The row's `accounting_fault` and the chain's `p426_accounting_faults` are added to that agreement **when present** (see §4 C1). An orphan sidecar or list entry refuses. `p426_signals.py:1915`: an accounting fault is a speed-invalid tier. `p426_signals.py:2068`: per-session runaway `tax` with accounting rows excluded, rendered `:2125`. Decode and walls already excluded them. | `test_b5_a_row_marker_contradicting_the_other_records_refuses`, `…accounting_slot_state_missing_refuses`, `…orphan_accounting_sidecar_refuses`, `…the_chains_accounting_list_must_agree`, `…accounting_fault_marks_its_leg_speed_invalid`, `…accounting_fault_row_leaves_the_runaway_tax`; invariant `…accounting_row_without_a_row_marker_stands_on_the_runners_records` | 6 failed (DID NOT RAISE ×4, assert False, KeyError 'tax'); invariant passed → all pass |
| B6 | `p426_verify.py:3062` CLI writes `B8.json` first (`write_atomic`), then B8-A8 in a second write. A refusal returns rc 2 and leaves `B8.json` in place. | `test_b6_b8_json_is_written_when_b8_a8_refuses` | FileNotFoundError (B8.json absent) → pass |
| B7 | `p426_verify.py:2914` `a8_utc_seconds`: an ISO string ending `Z` or with an offset is read as UTC; a naive time gives None. `_a8_latency` (`:2884`) refuses a row whose `t` does not parse or whose ms / CPU values are not finite, non-negative and non-bool. `p426_signals.py:1933` `_a8_time` delegates to it. | `test_b7_latency_times_are_utc_not_local` (TZ=America/New_York), `test_b7_a_latency_row_that_is_not_finite_non_negative_refuses[×5]` | 1795154400.0 ≠ 1795136400; 5 × DID NOT RAISE → pass |
| B8 | `test_m76_b4b1_impl_golden_tg1.py:31` `B4B2_CHANGED_INPUTS` lists exactly 16 `.b8.inputs.wave2/tg1-m76-{n16,x}-{pilot L0, reload L0, s1/s2/s3 L0+L1}…jsonl` paths, taken from a full `_diff` run with no allowance. The allowance (`:235`) matches only these exact paths. The assertion message now lists every diff. | `test_b8_the_tg1_golden_allows_only_pinned_input_paths` | AttributeError → pass; the golden itself passes |
| B9 | `p426_verify.py:2981` status is `complete` iff every confirmatory session is `accepted is True`. | `test_b9_a_rejected_confirmatory_session_leaves_the_record_incomplete` | 'complete' ≠ 'incomplete' → pass |
| B10 | `p426_verify.py:2712` `a8_seed_reasons`: `row.sampler_seed == rowschema.sample_seed(id, 0, TG2_P426_LEGS[session][1])`, else one REASON per attempt. | `test_b10_a_row_seed_not_the_plans_rejects_the_session`; invariant `test_b10_the_real_pilot_rows_carry_the_plans_seeds` | AssertionError [] → pass; invariant passed both times (the 8 real pilot rows match) |
| B14 | `p426_verify.py:2991` `STACK_REPO`; `check_b8_a8(rows_root, b8_a8, b8_sha256, repo_root)` (`:2994`) takes the repo root explicitly. The refusal names the missing input as "B8-A8 repo input <rel> is missing under the repo root …", with no absolute path. Callers: `p426_signals.py:1627` and `p426_panel.py:1867/2139` (`kv_a8_context(…, repo_root)`). | `test_b14_check_b8_a8_takes_the_repo_root_explicitly` | AttributeError (no STACK_REPO / 3-arg) → pass |
| B15 | `p426_verify.py:2411` `a8_applies` = lever kv and corpus tg2 only. A v8 whose arms are not `["n16", "x"]` stays a REASON, via the existing `v8_reasons`. | `test_b15_v8_arms_other_than_the_pair_is_a_reason_not_inapplicable` | assert False (refused as inapplicable) → pass |
| B16 | `p426_signals.py:1630` refuses when `b8_a8` is given without a 64-hex `b8_a8_sha256`; the canonical-JSON fallback is removed. The panel already used the file sha (`_kv_b8_a8`). | `test_b16_the_sheet_needs_b8_a8s_file_sha` | DID NOT RAISE → pass |

## 3. Conflicts with the frozen acceptance tests v2 (test directory read-only; for the test-writer / designer)

All 35 failures on the fix are listed in `../scratch/b4b2-final.txt`. Root causes:

1. **B4, about 30 tests: the frozen `World` v8 does not carry the identity its invocation manifests carry.** The manifests are the pinned real pilot ones; the v8 has no `probe_code_sha256`, `scaffold_policy_sha256` or `generation_identity_sha256`, and its `tg2_image_id` / `grader_image_id` are `sha256:555…`. Every A8 session is therefore rejected. Fix: copy the five values from `pinned_manifest(...)["runtime"]` into `_v8()`.
2. **B10, the same tests: `World.seed` is `SEED*100000 + hash`, not `rowschema.sample_seed(id, 0, seed)`.** The real runner uses `rowschema.sample_seed` (`opencode_common._item_seed`), and the real pilot rows match it. Fix: `seed = rowschema.sample_seed(rid, 0, SEED[session])`.
3. **B3: `test_manifest_of_a_discarded_rerun_attempt_is_not_an_orphan`.** The World's `harness_fault` slot attempt names no `invocation`; `chain_core.p426_record_fault` always records one. Fix: name the invocation, and give its manifest the faulted run's `run_id` (the r1fix `_rerun_world` shows how).
4. **B2 (and B10): `test_reload_control_refuses_when_seeds_differ`.**
   - `edit_row` rewrites a rows file without re-hashing its invocation record, so `load_slots` refuses ("sha256 differs").
   - Independently, after B10 a reload seed that differs from the plan's is a B8-A8 REASON. The reload is then never accepted, so the signals' "refused: seeds differ" control can no longer be reached (it stays as a defensive check).
   - The test's premise, that B8-A8 accepts a reload whose seeds differ from s1's, contradicts B10. **Designer call.**
5. The `conform()` helper in the r1fix file is a working reference for items 1 and 2: it re-seals v8, `frozen_record`, rows, invocation shas and accounting sidecars.

## 4. Choices and findings outside the ledger text

- **C1 (B5 deviation from the ledger's wording): the row marker is not required.** The ledger says "exact agreement (slot state, ledger, row, sidecar)". The runner never writes `accounting_fault` into a row: grep of non-test code shows it only in `chain_core` slot attempts (`:2912`, `:3226`), ledger entries (`:2915`, `:3235`) and `p426_accounting_faults` (`:2916`, `:3209`). Requiring a row marker would refuse every real accounting fault (AGENTS: guards check recorded facts). Implemented instead:
  - Slot state, ledger and sidecar must always agree.
  - The row marker and the chain list are bound whenever they are present, so a contradicting marker or list refuses.
  - An orphan sidecar or list entry refuses.
  - **Designer: confirm, or amend spec §9.4's "a row with `accounting_fault: true`".** The frozen World writes a row marker and no `p426_accounting_faults`; under this rule it stays consistent.
- **C2 (B2): `load_slots` errors refuse rather than become REASONs.** The ledger names `load_slots` as the authority and the spec has "only corrupted or contradictory records refuse". The frozen tests accept either outcome.
  - Effect on the candidate's own tests: two accepted attempts and a reason-less harness fault now refuse (they used to be REASONs).
  - `check_unregistered=False` plus an own check: an unregistered rows file that holds rows refuses. This is because the frozen all-DNF World writes empty, unregistered per-language rows files, and `load_slots`' own check would refuse those.
- **C3 (B3):** the run is bound through the invocation that the attempt names → its `.manifest.json` `run_id` → membership in `seen_run_ids`. Any missing link means no exemption.
- **C4 (B4):** the model has no v8 field, so it is bound to `schedule.picks[0]`, for the manifests and the rows. The image pins are bound through `runtime.policy.corpus_identity.image` and `runtime.policy.toolchain.grader_image_id` (the real manifest shape). `frozen_prompt_date` is not bound, because the ledger did not list it.
- **C5 (B5 tax):** the A8 section had no runaway-tax figure, so the "excluded from tax" part of the finding had nothing to apply to. I added a per-session `tax` (`_tax` with accounting rows removed, descriptive, no interval) and its sheet line. This is a new A8-section field, within the §7.2 projection.
- **C6 (B14):** both consumers pass `V.STACK_REPO`, the repo whose `TG2_DRAW_PATH` the producer read. The panel's `--repo` was not used for this.
- **C7:** an `a8_utc_seconds` time with no zone reads as None, so the latency row refuses and a leg window counts nothing.
- **C8:** the A7 loader now also computes `discarded_runs`. A7 has no harness faults, so it reads nothing extra. The A7 B8 facts are unchanged: the golden passes with the pinned allowance, and the committed-`B8.json` tests pass.
- **C9:** I changed the orphan reason's text to "not this slot's own discarded attempt" after the final full B4b-2 run. The red test and impl-verify files were re-run after that edit (86 passed).

## 5. Edits to existing tests (clause)

- `test_m76_b4b2_impl_world.py` (candidate 1's world):
  - invocation records for `load_slots` (B2);
  - `row_seed` = `rowschema.sample_seed` (B10);
  - `IDENTITY` in v8 and manifests (B4);
  - an accounting row carries the marker (B5);
  - the faulted attempt's run in `seen_run_ids` is its invocation manifest's `run-…` (B3).
- `test_m76_b4b2_impl_verify.py`:
  - `test_b8_a8_is_built_only_for_the_tg2_kv_pair` (B15: other arms are a reason; corpus tg1 is not applicable);
  - `test_a8_a_discarded_rerun_run_is_never_an_orphan` (B3: publishes under the invocation's run);
  - `test_a_slot_with_two_accepted_attempts_refuses` (B2: `load_slots` message);
  - `test_an_earlier_attempt_without_a_reason_is_a_reason` (B2: now a refusal);
  - `test_check_b8_a8_binds_the_base_b8_and_every_input` (B14: repo root);
  - `test_b8_a8_needs_a_base_sha` (B1: None → B8.json missing; a malformed sha still refuses).
- `test_m76_b4b2_impl_signals.py`:
  - `test_the_reload_control_asserts_equal_seeds` (B10: the reload is rejected, the control "not computed");
  - `test_a_rejected_confirmatory_session_is_incomplete` (B9);
  - `test_compute_kv_refuses_a_b8_a8_of_another_b8` (B14).
- `test_m76_b4b1_impl_golden_tg1.py`: B8 (above).

## 6. Files changed (working tree vs INDEX)

- `benchmark/bench/p426_verify.py`
- `benchmark/bench/p426_signals.py`
- `benchmark/bench/p426_panel.py`
- `benchmark/bench/tests/test_m76_b4b1_impl_golden_tg1.py`
- `benchmark/bench/tests/test_m76_b4b2_impl_world.py`
- `benchmark/bench/tests/test_m76_b4b2_impl_verify.py`
- `benchmark/bench/tests/test_m76_b4b2_impl_signals.py`
- new: `benchmark/bench/tests/test_m76_b4b2_impl_r1fix.py`

Scratch-only files (outside the stack): `../scratch/fix1-saved/` (copies of the three sources used for the before/after swap), `../scratch/seedcheck.py` (not run), and the logs `../scratch/*.txt`.

**Procedure for the "before" runs:** I wrote the INDEX versions of the three sources into the tree with `git show :path > path`, ran the red tests, then copied the fixed versions back. A stray copy accidentally written to `benchmark/p426_*.py` was removed immediately. `git status` shows only the intended files.

## 7. Commands and results (verbatim summary lines)

| run | command | result |
|---|---|---|
| Red tests on candidate 1 | `../fe_test.sh stack bench/tests/test_m76_b4b2_impl_r1fix.py -rA --tb=line` | `33 failed, 3 passed in 20.12s` |
| Revised B5 tests on candidate 1 | `… -k "b5"` | `6 failed, 1 passed, 31 deselected in 16.93s` |
| Red tests on the fix | `../fe_test.sh stack bench/tests/test_m76_b4b2_impl_r1fix.py` | `38 passed in 24.04s` |
| Red + impl-verify after C9 | `../fe_test.sh stack bench/tests/test_m76_b4b2_impl_r1fix.py bench/tests/test_m76_b4b2_impl_verify.py --tb=line` | `86 passed in 22.54s` |
| Golden + red (B8) | `../fe_test.sh stack bench/tests/test_m76_b4b1_impl_golden_tg1.py bench/tests/test_m76_b4b2_impl_r1fix.py` | `38 passed in 16.71s` (before the B5 revision) |
| All B4b-2 suites (frozen fe_b8/panel/real/signals/support + impl golden/panel/signals/verify/world + r1fix + tg1 golden) | — | `35 failed, 239 passed, 1 skipped in 530.98s`. The 35 are the frozen conflicts in §3. The skip: "the tg2 pilot pair's evidence objects are not on origin/evidence in this clone". |
| Frozen 140, B4/B10 neutralised | — | `2 failed, 138 passed in 301.50s` (`test_manifest_of_a_discarded_rerun_attempt_is_not_an_orphan`, `test_reload_control_refuses_when_seeds_differ`) |
| Frozen accounting / rerun / harness / orphan tests, neutralised, after the B5 revision | — | `1 failed, 12 passed, 83 deselected` (the B3 conflict) |
| Families: `test_m76_b3_*` (incl. `impl_a7`), `test_m76_b8_*`, `test_s26_p17`, `test_s26_p15` | — | `3 failed, 728 passed, 1 skipped in 605.08s`. All 3 are in `test_m76_b3_impl_golden_mtp.py` and name the absent `f2b61127…`. |
| Families: `test_m76_b4b1_*`, `test_p426_*`, `test_t3_*` | — | `1 failed, 969 passed in 3827.46s`: `test_m76_b4b1_fe_golden_tg1.py::test_b8_regenerates_byte_identical`, which names the absent `f2b61127…` |
| Families: `p613`, `p613s2`, `p613s3`, `p613s4` | — | `860 passed, 22 skipped in 4436.76s` |
| Earlier combined family run (superseded) | — | Stopped at its 1 h background limit at ~85%, with 2 unnamed `F`s. It was rerun as the two runs above, which together show only the one `f2b61127` failure. **The second earlier `F` did not reproduce, and it is not identified.** |

## 8. Not satisfied / open

- **Frozen suite: 35 / 140 fail on the fix** because of fixture conflicts with B4, B10, B3 and B2 (§3). They need the test-writer's fixture changes, plus a designer call on `test_reload_control_refuses_when_seeds_differ`.
- **B5 deviation (C1)** needs designer confirmation.
- **B11 / B12** belong to the designer and test-writer. `_a8_packet` / `kv_export` on real bytes were not exercised here.

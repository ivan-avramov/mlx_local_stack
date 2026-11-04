Delivery 3 is done. I amended the 12 defective tests and added the new ones. Against the unfixed candidate, 20 tests fail, all of them fix tests, and 90 pass with 2 skipped.

## Files changed (`benchmark/bench/tests/p613s4/` only)
- **`test_p613s4_binding.py`** (rewritten): the binding refusals now run at the `_events` level, on an in-memory copy of the verified attempt and row.
  - `test_harvest_binding_refused` covers 8 modes: wrong `published_sha256`, wrong raw `sha256`, duplicate record, missing record, raw sha used as published sha, row sha mismatch, row without a sha, and destination not `evidence`.
  - `test_events_control_binds` is the control.
  - `test_unparseable_events_refused` calls `parse_messages` on 3 bad inputs: non-JSON, invalid UTF-8, a truncated second line.
  - `test_edited_harvest_on_disk_rejects_pair` pins the closed route: an edited HARVEST makes B8 reject the pair, the section is `complete: False`, and the file is never compared.
- **`dview.py`**: `divergence_flags` now matches only the A7 first-divergence flag (text "first divergence" or `flag == "a7_divergence_generation"`), so the committed `cross_wave` flag no longer counts.
- **`s4world.py`**: new `C:<variant>` worlds (`no_input`, `no_output`, `no_state`). One OFF events file of `s1 python/alpha` is damaged; the world is still HARVEST-bound and hash-correct.
- **`test_p613s4_golden.py`**:
  - `test_golden_cli_final` now expects `header.evidence_ref` to be the resolved full sha, and 172 inputs under `evidence:<full sha>:`.
  - New `test_golden_evidence_ref_given` expects `evidence_ref_given == "b6ec7819"`.
  - New `test_golden_section_between_subjective_and_flags` (F4, on the generated real sheet).
  - New `test_golden_committed_sheet_section_position` (F4 on the committed sheet; skips until step 4 commits it).
- **`test_p613s4_fixes.py`** (new, 52 test cases):
  - Fix 1: three damaged-event worlds through `a7_divergence` (the refusal must name `python/alpha`), plus three `parse_messages` cases, plus a complete-events control.
  - Fix 2: `_final_ready` on the hermetic record, with each of 5 axes missing `b1` or `b2` (10 cases), plus unaccepted-block cases.
  - Fix 3: `evidence_ref_given` for a short and a full passed ref.
  - Fix 4: `--evidence-ref` without `--panel` must give rc 2, `REFUSED` mentioning `--panel`, and no output files.
  - F2: a B8-rejected A7 session.

## Run on the unfixed candidate
Command, from `benchmark/`: `../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/p613s4`

Result: `20 failed, 90 passed, 2 skipped in 356.74s`.

| Failing tests | Count | Reason |
|---|---|---|
| Fix 1: `test_tool_event_without_required_state_refused` (3) and `test_parse_messages_refuses_damaged_tool_event` (3) | 6 | "no refusal was raised" |
| Fix 2: `test_axis_missing_a_block_is_not_final`, 5 axes × `b1`/`b2` | 10 | `_final_ready` returns `{'ready': True, 'missing': []}` |
| Fix 3: `test_evidence_ref_given_is_as_passed` (short, full) | 2 | no `evidence_ref_given` in header or divergence |
| Fix 3: `test_golden_evidence_ref_given` | 1 | `KeyError: 'evidence_ref_given'` |
| Fix 4: `test_ref_without_panel_refuses_rc2` | 1 | candidate exits 0 |

- **Passing:** the 11 re-aimed binding tests, the amended `test_golden_cli_final`, and the F2 test. F2 passes on the candidate: a B8-rejected `s1` is not FINAL, `header.final.missing` names `A7-s1`, and `divergence.complete` is false.
- **Skipped (2):** `test_golden_committed_sheet_is_the_final_output` and the new committed-sheet position test. Both skip, with the reason stated, until step 4 commits its sheet. This is why F4 is checked on the generated sheet now.

## Reading and weak spots
- **Where `evidence_ref_given` lives:** I read the brief as "next to `evidence_ref`", so `header.evidence_ref_given`. The hermetic test also accepts it in the `divergence` record. The golden test requires it in the header.
- **Test vacuous on the candidate:** `test_short_and_full_ref_differ_only_in_given` passes on the candidate because neither run has the key (it pops it if present). It becomes meaningful after fix 3.
- **`_events` and `parse_messages`:** the binding and fix-1 parser tests call these candidate functions directly, as the brief says. If the fixed implementation renames them, those tests fail on the import, not on behaviour.
- **F2 construction:** I build the rejected session by editing `s1`'s HARVEST (B8 rule 5 rejects the pair), re-verifying and committing B8, then exporting and judging a fresh panel on that copy. That is the only hermetic route I found to a B8-rejected session. It also verifies that `all` still runs end to end with a rejected session, which the unit-level checks do not.
- **Last assertion of the F2 test:** it checks that `"A7-s1"` appears somewhere on the sheet. It is weak and not specific to the Final line. The specific checks are the three above it.

The unfixed candidate is untouched, and I committed nothing. Writes were limited to `benchmark/bench/tests/p613s4/`.

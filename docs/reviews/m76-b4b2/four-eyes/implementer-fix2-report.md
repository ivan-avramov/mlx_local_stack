# M76 B4b-2 — implementer fix round 2 report (review r2 of 3; spec v1.5)

Fixed: D1–D4 of `change-ledger-r2.md`. D5 (declined) and D6 (covered) were not touched. Nothing was staged, committed, reset or pushed.

## Per finding

| id | change (file:line) | red test (`bench/tests/test_m76_b4b2_impl_r2fix.py`) | candidate 2 | fixed tree |
|---|---|---|---|---|
| D1 | `benchmark/bench/p426_verify.py:2556-2585` (`_a8_accounting`): a `p426_accounting_faults` that is present must be a list. Every entry must be an object with a str `slot` and a `rerun_index`, name the sidecar `items/<record_name(slot,k,"accounting.json")>`, and be unique per (slot, k). Each accepted row slot needs exactly one `kind=="row"` ledger entry at its (slot, rerun index), and that entry's marker joins the agreement check, which replaces `any(...)`. | `test_d1_accounting_records_bind_exactly` [contradictory duplicate ledger entry; duplicate list entry; non-object list entry; list entry naming another sidecar; list entry without sidecar], `test_d1_a_row_without_its_ledger_entry_refuses`, plus the control `test_d1_control_the_runners_accounting_records_are_accepted` | 6 FAIL (control passes) | pass |
| D2 | `p426_verify.py:2949-2954` (`a8_utc_seconds`): a zoned ISO time must give a finite, non-negative epoch, the same rule as numeric `t`. `OverflowError` (e.g. `0001-01-01T00:00:00+01:00`) now gives None instead of a traceback. | `test_d2_an_iso_time_before_the_epoch_is_not_a_utc_time` [1969-12-31T23:59:59Z, 1900-01-01T00:00:00+00:00, 0001-01-01T00:00:00+01:00]: the helper returns None and the latency record refuses | 3 FAIL | pass |
| D3 | `p426_verify.py:2716-2730` (`a8_v8_identity_reasons`): `want_model = ENTRY`. A new REASON fires unless `schedule.picks[0] == ENTRY`. Manifest and row model mismatches are now reported against "the registry pick". Docstring at :2714 updated. | `test_d3_the_model_is_bound_to_the_registry_pick_not_the_schedule`: schedule, manifests and rows all name `another-model` and agree with each other | FAIL (accepted) | pass |
| D4 | `p426_verify.py:2540-2544` new `_a8_rerun_index` (`type(x) is int and x >= 0`, else `RefusalError`). It is used for ledger entries (absent key → 0, as the runner writes rerun 0) and for list entries (key required; the runner always writes it). | `test_d4_a_malformed_rerun_index_is_a_refusal` [ledger, list] × ["x", [0], 1.5, True, -1] | 10 FAIL (ValueError/TypeError tracebacks or wrong refusal) | pass |

## Other file changed

- `benchmark/bench/tests/test_m76_b4b2_impl_r1fix.py` (`test_b5_an_accounting_row_without_a_row_marker_stands_on_the_runners_records`, `test_b5_the_chains_accounting_list_must_agree`): the hand-built `p426_accounting_faults` entries now carry the `sidecar` field, as the runner writes them (`chain_core.py:2916-2917`, `:3209-3211`). This is an implementer test added in candidate 2. Without the change, D1's sidecar requirement would refuse these entries for the wrong reason. No frozen test was edited.

Files changed: `benchmark/bench/p426_verify.py`, `benchmark/bench/tests/test_m76_b4b2_impl_r1fix.py` (edited); `benchmark/bench/tests/test_m76_b4b2_impl_r2fix.py` (new, untracked).

## Commands and results (verbatim summary lines)

1. `../fe_test.sh stack bench/tests/test_m76_b4b2_impl_r2fix.py` on the fixed tree → `21 passed in 9.92s`
2. Red check: I saved the fixed `p426_verify.py` to scratch, wrote `git show :benchmark/bench/p426_verify.py` (the candidate 2 INDEX copy) into the working tree, then ran `../fe_test.sh stack bench/tests/test_m76_b4b2_impl_r2fix.py` → `20 failed, 1 passed in 55.05s` (the 1 pass is the D1 control). I then restored the fixed file: `git diff --stat` shows p426_verify.py +40/−13, as expected. The scratch copy `../scratch/p426_verify.fix2.py` is still there because the `rm` was not approved in this session; it can be deleted.
3. `../fe_test.sh stack` on the seven `test_m76_b4b2_impl_*.py` files → `153 passed, 1 skipped in 188.02s`. The skip is `test_m76_b4b2_impl_golden.py:127: the tg2 pilot pair's evidence objects are not on origin/evidence in this clone`.
4. `../fe_test.sh stack` on all `test_m76_b3_*`, `test_m76_b4b1_*` and `test_p426_*` files (50 files) → `4 failed, 1276 passed, 2 warnings in 485.24s`. The 4 failures:
   - `test_m76_b3_impl_golden_mtp.py::test_mtp_golden_is_meaningful`
   - `test_m76_b3_impl_golden_mtp.py::test_mtp_golden_component[leg_checks]`
   - `test_m76_b3_impl_golden_mtp.py::test_mtp_golden_committed_b8_and_signals_regenerate`
   - `test_m76_b4b1_fe_golden_tg1.py::test_b8_regenerates_byte_identical`

   All four stop at `REFUSED: frozen stack_head_on f2b61127c55f0436b6c6c777bec5384ce004d62d does not resolve: git rev-parse failed`. That commit is not in this copy. These are the `f2b61127…` goldens that ledger D6 assigns to the stack gate. The refusal comes before any of my changed code runs, but I did not rerun these four on candidate 2 to prove it.

No whole suite, server, model, GPU or benchmark leg was run.

## Choices (for the reviewer)

- C1 (D1): the "exactly one ledger entry" check applies to **every** accepted row slot, not only accounting-fault rows. A row with no ledger entry used to pass silently (`any([]) == False` agreed with "not a fault"). The real pilot records fit: 4 rows and 4 `kind:"row"` entries per arm.
- C2 (D1): a list entry must carry `rerun_index` explicitly, because the runner always writes it. A ledger entry may omit it (meaning 0), because the runner omits it at rerun 0 (`chain_core.py:2915`).
- C3 (D4): negative integers are refused too, along with bools, floats, strings and lists. Recorded rerun indices are never negative.
- C4 (D3): a schedule whose first pick is not `ENTRY` is a REASON (session rejected), not a refusal. This matches the other rule-3.6 bindings in the same validator.
- C5: an absent `p426_accounting_faults` key stays allowed, as in r1. The real pilot chains predate the list.

## Questions

- Q1: may the operator or test-writer confirm that editing the implementer-owned `test_m76_b4b2_impl_r1fix.py` was in scope? The brief says the test directory is read-only except for the new r2fix file. I took the r1fix test to be among "the files candidate 2 added".

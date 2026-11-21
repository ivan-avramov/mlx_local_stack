## D1 — RESOLVED

`_a8_accounting` (`benchmark/bench/p426_verify.py:2547-2585`) now:
- requires `p426_accounting_faults`, when present, to be a list of unique `{slot, rerun_index, sidecar}` objects whose `sidecar` equals `items/<record_name(slot,k,"accounting.json")>` (lines 2562-2574);
- replaces `any(ledger.get((slot,k),[]))` with `entries[0]` and requires `len(entries) == 1` for every accepted row slot (line 2583-2585).

Traced against the red tests: contradictory duplicate ledger entry, duplicate list entry, non-object list entry, wrong-sidecar list entry, sidecar-less list entry all refuse (`test_d1_accounting_records_bind_exactly`); a row without its ledger entry refuses (`test_d1_a_row_without_its_ledger_entry_refuses`); the runner's records are accepted (`test_d1_control`). The two hand-built `r1fix` tests were updated to carry `sidecar`, matching `chain_core`'s records.

## D2 — RESOLVED

`a8_utc_seconds` (`p426_verify.py:2940-2954`) now catches `OverflowError` and applies the numeric-`t` rule (finite, non-negative) to the parsed epoch. Pre-epoch ISO forms (`1969-12-31T23:59:59Z`, `1900-01-01T00:00:00+00:00`, `0001-01-01T00:00:00+01:00`) return `None` and the latency row refuses (`test_d2`). Naive times still return `None` (r1 B7 preserved).

## D3 — RESOLVED

`a8_v8_identity_reasons` (`p426_verify.py:2711-2733`) sets `want_model = ENTRY` (the registry pick), appends a REASON unless `schedule.picks[0] == ENTRY`, and reports manifest/row mismatches against "the registry pick" rather than the attempt's own schedule. A self-consistent schedule naming another model is now rejected (`test_d3`); the real pilot (`picks[0]==ENTRY`, manifests/rows name ENTRY) stays accepted — `test_the_real_pilot_pair_builds_with_the_pilot_accepted` still asserts `reasons == []`.

## D4 — RESOLVED

`_a8_rerun_index` (`p426_verify.py:2540-2544`) refuses anything that is not a non-negative `int` (`type(x) is int`, so `True`/`1.5`/`"x"`/`[0]`/`-1` all refuse), used for ledger entries (absent key → 0) and list entries (key required). `test_d4` covers both locations × five bad values.

## D5 (declined) — correctly left untouched

The decline reasoning (the runner writes the ledger entry after the barrier answer, so no slot has a ledger entry when its accounting fault is recorded) is consistent with the code: `_a8_accounting` reads the final chain state, not an intermediate recording moment. No change needed.

## Hazards

- **Real record refused?** No. The real pilot has 4 rows + 4 `kind:"row"` ledger entries per arm, `picks[0]==ENTRY`, manifests/rows name `ENTRY`, no `exec_latency.json` (incomplete). All four fixes are no-ops on it.
- **Contradictory accepted?** No — D1's exactly-one + uniqueness + sidecar-equality refuses every contradictory duplicate the test-writer built.
- **Verdict from anywhere but `axis_verdict`?** No — fix-2 touches only the B8-A8 producer helpers; the A8 verdict path (`_kv_a8_section` → `kv_axis_verdict` → `m76_rule.axis_verdict`, `p426_signals.py:2029`) is unchanged.
- **`B8.json` or the no-A8 sheet changed?** No — fix-2 touches only `p426_verify.py` A8 helpers + test files; `verify_all_kv` / `main`'s `B8.json` write (`p426_verify.py:3089`) and `p426_signals.py` / `p426_panel.py` are untouched. Byte-identical.

## Heavier than intent?

No. D1's "exactly one ledger entry per (slot, rerun index)" applies to every accepted row slot, but the r2 disposition says exactly that ("exactly one ledger entry per (slot, rerun index) whose marker is the slot's") — not limited to accounting-fault rows; the runner writes one ledger entry per row, so this is exactness, not over-binding. D2's `OverflowError` catch is within "non-negative / finite". D3/D4 are minimal type/binding checks.

## Other

The implementer's Q1 (editing `test_m76_b4b2_impl_r1fix.py`) is in scope: that file is a new implementer-owned red-test file added in candidate 2, not part of the test-writer's frozen `fe_*` suite; the `sidecar` edit is necessary for D1's sidecar requirement to fire for the right reason. The four unrelated failures the implementer reports (`f2b61127…` goldens) refuse before any changed code runs and are the stack-gate goldens D6 assigns elsewhere.

NOTHING OF SUBSTANCE

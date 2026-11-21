# Test-writer report, delivery 4 (last) — M76 B4b-2, fix round 2 (candidate 3 = candidate 2 + `fix-2.patch`)

Commands: `../fe_test.sh stack …` (candidate 3), `../../twb/fe_test.sh stack …` (baseline copy; `test_m76_b4b2_fe_r2.py` copied there). Nothing committed, pushed or reset.

## 1. Result

| set | baseline | candidate 3 |
|---|---|---|
| v3 set, 6 files, 159 tests (unchanged) | 34 passed · 114 failed · 11 errors | **159 passed** (470 s) — no v3 test fails: no (D), no (I) |
| new `test_m76_b4b2_fe_r2.py`, 32 tests | 32 failed (no A8 interfaces) | **32 passed** |
| whole set, 7 files, 191 tests | 34 passed · 146 failed · 11 errors | **191 passed** |

Outputs: `../scratch/tw4_cand3_v3.txt`. The 34 baseline passes are the same invariants as in v3.

One related run (not my set): the implementer's seven `test_m76_b4b2_impl_*` files on candidate 3 beside my v3 `World`: **1 failed, 152 passed, 1 skipped** —
`FAILED bench/tests/test_m76_b4b2_impl_r1fix.py::test_b2_a_rows_file_changed_after_validation_refuses` (`Failed: DID NOT RAISE RefusalError`, r1fix.py:125).
Cause: a fixture conflict, not a candidate defect — that test calls `w.edit_row(...)` expecting the v2 `edit_row`, which did not re-hash the invocation record; the v3 `edit_row`
re-hashes it (brief item B2), so the rows file is consistent and nothing refuses. The intent (a rows file changed behind its invocation record refuses) holds on candidate 3 and is
tested in my `test_b2_a_rows_file_changed_behind_its_invocation_record_refuses` (writes the file directly). The implementer's test needs the same one-line change (edit the file, not `edit_row`) when the v3 suite is merged.

## 2. New tests (`test_m76_b4b2_fe_r2.py`; the implementer's `r2fix` covers each finding once, these are the scenarios it does not)

* **D1** — an accounting fault on an accepted **rerun** (index 1) with slot state, ledger, sidecar `.r1` and chain list agreeing is accepted and listed (b); a second contradicting ledger
  entry at the accepted rerun index refuses (a); the ledger entry at the faulted attempt's index (0) leaves none at the accepted one: refuses (a); a chain-list entry at the other rerun index refuses (a);
  a chain list that is `{}` / `"none"` / `0` refuses (a); a list entry for a row without a fault refuses (a); an empty list with no fault stands (b).
* **D2** — the epoch itself, `+01:00` at the epoch and `+02:00` are valid UTC times (b); `1969-12-31T18:59:59-05:00`, `…23:59:59.999Z`, `1970-01-01T00:59:59+01:00` (before the epoch in UTC whatever the written offset) refuse in the latency record (a); numeric `t`: 0 stands, −1 / NaN / −5 refuse (b).
* **D3** — one arm alone naming another model than the registry pick is rejected (a); a schedule whose first pick is not the registry pick (manifests and rows on it) is rejected by its picks (a); the registry pick everywhere is accepted (b).
* **D4** — a rerun index `"0"`, `"1"`, `None`, `{}`, NaN in the ledger or in the list is a `RefusalError`, never another exception type (a); a ledger entry that omits `rerun_index`, or has the integer 0, means rerun 0 (b).
* **B2 (intent kept)** — a rows file changed behind its invocation record refuses (`sha256 differs`) (a).

## 3. Review of fix 2 against D1–D6 and the spec

**Verdict: merge.** D1–D4 are implemented as ruled, D5 (declined) and D6 (covered) untouched; the real pilot records still pass (`test_m76_b4b2_fe_real.py`, 18 tests, on candidate 3). I found no defect.

| id | read in `fix-2.patch` | result |
|---|---|---|
| D1 | `_a8_accounting`: the chain list must be a list; every entry an object with a str `slot` and an explicit `rerun_index`, naming exactly `items/<record_name(slot,k,"accounting.json")>`, unique per (slot, k); exactly one `kind=="row"` ledger entry at (slot, accepted index) for **every** accepted row, whose marker joins the agreement | as ruled; my rerun-slot scenarios (index 1) pass, which the implementer's pilot-only tests do not reach |
| D2 | `a8_utc_seconds`: a zoned ISO time must be finite and `>= 0` after conversion; `OverflowError` → None | as ruled; boundary (epoch 0 valid, 1 s before refuses, offset forms) pass |
| D3 | `want_model = ENTRY`; a schedule whose first pick is not `ENTRY` is a REASON; manifest and row models compared with `ENTRY` | as ruled; one-arm and schedule-only deviations are both caught |
| D4 | `_a8_rerun_index`: `type(x) is int and x >= 0`, else `RefusalError`; used for ledger (absent → 0) and list entries | as ruled; strings, `None`, dicts, NaN all refuse cleanly |

Remarks (none blocking):

| id | sev | where | note |
|---|---|---|---|
| g1 | minor | `p426_verify.py` D1 (C1) | "exactly one ledger entry per accepted row" is now a refusal for **every** row, not only accounting faults: a chain whose ledger lacks a row entry (e.g. an older runner, or a hand-edited chain) is refused wholesale. Consistent with the real pilot (4 rows, 4 entries per arm) and with the runner's done path; keep, and mention it in the spec's §9.4 wording |
| g2 | minor | D3 | the model is now the constant `ENTRY` in `p426_verify`; an A8 run of another registry pick would be rejected until that constant moves. Intended by the ruling; note it for the next model |
| g3 | note | carried from delivery 3 | f1–f4 (cheat-rerun orphans on tg1, stale `B8-A8.json` after an A8 refusal, tz-naive leg windows printing `n: 0`, `STACK_REPO` as the draw root) were not adopted in r2 and are unchanged |
| g4 | process | `test_m76_b4b2_impl_r1fix.py` | the implementer edited this implementer-owned test (adding the `sidecar` field its hand-built list entries now need): reasonable, it is a candidate-2 file, no frozen test was touched. Separately it contains the one test that conflicts with the v3 `edit_row` (§1) |

## 4. Not run

I did not rerun the existing test families (`test_m76_b3_*`, `test_m76_b4b1_*`, `test_p426_*`, `p613*`, `test_m76_b8_*`, `test_s26_p1*`, `test_t3_*`) on candidate 3. The implementer reports `4 failed, 1276 passed` for `b3` + `b4b1` + `p426`, all four naming the absent commit `f2b61127…` (stack gate, ledger D6); I have not verified that. `p613*` and the `m76_b8` / `s26` / `t3` families remain unrun to completion by me since delivery 2 (stopped at the background limit).

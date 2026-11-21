## B1–B16 disposition in candidate 2

| id | verdict | trace |
|---|---|---|
| B1 | resolved | `verify_a8_kv` derives the base sha from `<results_root>/B8.json` and refuses if the file is absent. The CLI passes the sha explicitly (`p426_verify.py:2930–2946`, `:3062`). |
| B2 | resolved | `_a8_inventory` sits on `chain_rows.load_slots(check_unregistered=False)` plus the extra checks. `load_slots` errors refuse (C2). I traced the real runner shapes in `chain_core` (`p426_harness_dnf_record`, `p426_record_fault`); they pass. The harness-DNF sidecar is the same sealed record as chain.json's, so `doc == s.row` holds on real data. |
| B3 | resolved | `discarded_runs` follows slot attempt → invocation → `manifest` → `run_id` → `seen_run_ids`, and `final_tree_reasons` exempts only `(rid, other)`. The real invocation records carry `manifest` (`INV_KEYS`). Rerun slots are not affected. |
| B4 | partly resolved | See P1. The identity, pin and image checks are bound. The model is not bound to anything external. |
| B5 | resolved | Slot state, ledger and sidecar must agree. The row marker and chain list are bound when present, and orphan sidecars refuse. This matches the runner's writes (`chain_core:2910–2917`, `:3195–3236`), so C1 does not refuse real faults. The leg is marked speed-invalid and tax excludes accounting rows. `tax` appears only in the A8 section, so the no-A8 sheet is unchanged. |
| B6 | resolved | `B8.json` is written first. A B8-A8 refusal returns rc 2 and leaves `B8.json`. A stale B8-A8 is refused by its `base_b8_sha256` binding. |
| B7 | resolved | `Z` and offset strings parse as UTC, which matches `utc_stamp`. Latency rows are validated for finite, non-negative numbers. |
| B8 | resolved | I did not re-run the golden. The report says it passes with the pinned paths. |
| B9 | resolved | The status is `complete` only when every confirmatory session is accepted. |
| B10 | resolved | `TG2_P426_LEGS["reload"]` seed is 1001, the same as s1. The row seed ignores the rerun index (`_item_seed` uses 0), so reruns are not refused. The "seeds differ" control in signals is now unreachable but harmless. |
| B11 | not in this diff | Covered by the designer, pending the new-identity pilot. |
| B12 | not in this diff | Test-writer's delivery 3. |
| B13 | declined | Agreed. |
| B14 | resolved | `STACK_REPO` is `parents[2]` of `p426_verify.py`, which is the repo root. It is the same repo the producer reads the draw from. Both consumers pass it. |
| B15 | resolved | The arms mismatch is now a REASON through `v8_reasons`. |
| B16 | resolved | The file sha is required and the fallback is gone. |

I found no verdict path outside `axis_verdict`, no change to `B8.json` or the no-A8 sheet, and no way for the panel to judge an unbound item. The panel diff only threads `repo_root`.

## Findings

**P1. Minor (confirmed in source; consequence hypothesis): B4 binds the model only to the attempt's own schedule.**
- Location: `p426_verify.py:2693`, `a8_v8_identity_reasons`.
- Problem: `want_model = att["schedule"]["picks"][0]`. `schedules.check_tg2_p426` also takes `model` from `schedule["picks"][0]`, so the check compares the schedule to itself. `ENTRY` (`:639`) is never compared.
- Failure scenario: two legs run on another model with a self-consistent schedule pass the model check. Only the probe-code, scaffold and generation-identity shas in v8 could catch it, and I did not verify that `generation_identity_sha256` covers the model.
- Proposed change: `want_model = ENTRY` and also require `schedule.picks[0] == ENTRY`. Alternatively, confirm and document that `frozen_record` or the generation identity pins the model.

**P2. Minor (confirmed): `_a8_accounting` can crash on a malformed `rerun_index`.**
- Location: `p426_verify.py:2552` and `:2555`.
- Problem: `int(e.get("rerun_index") or 0)` raises `ValueError` or `TypeError` on a malformed value. That is an uncaught traceback, not a `RefusalError`, and the CLI's rc 2 path is skipped.
- Proposed change: use `type(x) is int` and raise `RefusalError`, as `validate_progress` does.

**P3. Minor (hypothesis): an accounting fault on a slot whose ledger entry already exists would be refused.**
- Location: `chain_core.py:2910–2917`, read against `_a8_accounting`.
- Problem: when the failing slot is already in the ledger, the runner still appends the sidecar and the `p426_accounting_faults` entry. It adds no accounting-marked slot attempt or ledger entry in that case. Slot state and ledger would then be false while the sidecar and chain list are true, so `len(set(marks.values())) != 1` refuses.
- Why it is only a hypothesis: I could not construct a runner path that reaches this, because the ledger is written after the barrier answer.
- Proposed change: ask the designer whether this shape is reachable. If it is, treat "sidecar plus chain list present, slot and ledger absent" as a real fault.

**P4. Leftover state, not a defect in the diff.**
- The 35 frozen tests (v2) still fail on candidate 2. They are fixture conflicts with B4, B10, B3 and B2, and the test-writer is amending them.
- The reload test needs a designer call, because B10 makes its premise unreachable.
- The implementer's earlier combined run showed one unidentified `F` that did not reproduce.
- The three `test_m76_b3_impl_golden_mtp` failures and `test_m76_b4b1_fe_golden_tg1::test_b8_regenerates_byte_identical` name the commit `f2b61127…` that is absent from the clone. I could not verify that `B8.json` stays byte-identical on those. Re-run them where that commit exists before the freeze.

**P5. Minor, weight only.** `_a8_inventory` calls `reader.read_bytes` once per row for the same rows file. The input record dedupes, so it is only repeated work, not wrong.
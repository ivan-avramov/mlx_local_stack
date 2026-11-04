I've completed my review. Here are my findings.

---

## Findings

### F1 — `--panel` is required; E1 makes it optional (blocker)

**Location:** `benchmark/bench/p426_signals.py` `main()`, lines ~1209–1210 (candidate.diff lines 870–871).

```python
if args.axis == "all" and args.panel is None:
    raise RefusalError("--panel <dir> is required (step 3: the sheet carries the §4.5 subjective section)")
```

**Severity:** blocker. **Evidence:** confirmed (traced in source; implementer's report corroborates — "12 failed … all 12 failures have the same cause").

**Problem:** Erratum E1 settles that `--panel` is OPTIONAL: absent → `all` writes the step-2 record unchanged (status `PROVISIONAL — subjective panel pending (step 3)`); present → §4.5 + status `PROVISIONAL — final review pending (step 4)`. The candidate refuses when `--panel` is absent. This breaks the 12 committed step-2 CLI/golden tests (`test_p613s2_all_cli.py`, `test_p613s2_golden.py`) that run `all` without `--panel` and expect rc 0 with the step-2 header/status. The step-2 golden "committed outputs are the `all` outputs" cannot pass against this candidate. The in-process `compute_all(..., panel=None)` path is correct (returns the step-2 record unchanged); only the CLI gate is wrong.

**Failure scenario:** Any operator or CI run of the step-2 golden suite against this candidate gets rc 2 + `REFUSED: --panel <dir> is required …` instead of the committed `SIGNALS.md`. The step-2 contract's "Committed outputs become the `all` outputs" is unverifiable.

**Proposed change:** Delete the `if args.axis == "all" and args.panel is None: raise` block. The `compute_all(panel=None)` path already returns the step-2 record, so the CLI just needs to pass `panel=args.panel` (already done) and let `None` flow through. Keep the missing-FROZEN.json refusal (it already lives in `check_frozen` via `a7_ingest`).

---

### F2 — Wave 1 A1 panel-identical count is 100, not 96; the 4 both-wrong keys are silently dropped (major)

**Location:** `benchmark/bench/p426_panel.py` `wave1_identity()` (lines ~664–681) and `benchmark/bench/p426_signals.py` `compute_subjective()` Wave 1 branch (lines ~991–1001).

**Severity:** major. **Evidence:** confirmed (traced in source; implementer's report P5 acknowledges the choice: "I report A1 as 100 identical keys … That includes the 4 keys where both arms are wrong, even though the spec's selection rule for A1 is 'both correct'").

**Problem:** Erratum E3 settles that the panel's A1 identity is the **panel-eligible set** (`select`'s both-correct rule): 96 keys, all identical; the 4 both-wrong keys are "not both correct", excluded and counted. Wave 1 identical over eligible keys = A1 96 + A2 40 + A3 20 + A4 6 = **162** (166 B8 keys; 4 not eligible). The candidate instead sums `identical.n` over all B8-accepted Wave 1 pairs, giving A1 = 100 and a total of **166**. The 4 both-wrong A1 keys are neither excluded nor counted anywhere in the §4.5 member record (the Wave 1 member sets `one_arm_pass_left_out=0` and has no "not both correct" / "neither-pass" field). So the §4.5 Wave 1 A1 row reports `identical=100, keys=100` and silently drops the 4 both-wrong keys, contradicting E3 and the spec's "Every member is labelled 'conditional on both-pass' with n and the count of one-arm-pass items left out" (here the analog is "not both correct").

**Failure scenario:** The operator reads `SIGNALS.md` §4.5 and sees A1 `identical 100 / keys 100`, inferring all 100 panel-eligible A1 keys were identical and none were excluded for not being both-correct. Per E3 the correct numbers are 96 identical, 4 "not both correct" excluded. The frozen `wave1_identical` count is also 166 instead of 162. This is a §4.5 number that is wrong.

**Proposed change:** In `wave1_identity` (or a new panel-eligible helper), apply the A1 both-correct rule: for A1, count only keys that are both-correct (the `select` rule), and put the both-wrong keys into an `excluded["not both correct"]` count. For A2/A3/A4 the eligible set is all accepted keys (as today). Store the eligible identical total (162) in `wave1_identical`. In `compute_subjective`'s Wave 1 branch, source A1's `identical`/`keys` from the eligible set, not from `signals.identity` (which is all B8 keys), and add a `not_both_correct_left_out` count.

---

### F3 — Frozen tests miss F1 and F2 (major)

**Location:** `.p613-material/frozen-tests/test_p613s3_signals.py` (no `--### F3 — Frozen tests miss F1 and F2 (major)

**Location:** `.p613-material/frozen-tests/test_p613s3_signals.py::test_panel_option_is_required`; `test_p613s3_golden.py::test_golden_export_84_verdicts_planned`.

**Severity:** major. **Evidence:** confirmed (traced in source).

**Problem:** Two gaps:
- `test_panel_option_is_required` asserts `all` without `--panel` refuses. This locks in the pre-E1 behavior and would have to be inverted (assert rc 0 + step-2 status) once E1 is applied — the test encodes the wrong invariant.
- `test_golden_export_84_verdicts_planned` asserts `166 in nums` in FROZEN.json. Per E3 the panel-eligible identical total is 162, not 166. The test encodes the wrong golden number and would mask the F2 fix.

**Failure scenario:** A future implementer applies E1/E3 correctly; these frozen tests fail and are treated as regressions rather than stale-oracle updates.

**Proposed change:** Replace `test_panel_option_is_required` with two tests: (a) `all` without `--panel` → rc 0, step-2 header/status; (b) `all` with a missing FROZEN.json → rc 2 + REFUSED. Change `166` to `162` in the golden test and add an assertion that A1's panel-eligible identical is 96 with 4 "not both correct" excluded.

---

### F4 — `missing_verdicts = planned - valid` can go negative on duplicate verdicts (minor)

**Location:** `benchmark/bench/p426_signals.py` `compute_subjective()`, line ~1036: `missing_verdicts=planned - valid`.

**Severity:** minor. **Evidence:** confirmed (traced in source).

**Problem:** `valid = sum(valid_by_item.get(it, 0) for it in s_items)` counts every verdict with a valid choice, including duplicates. `planned = len(s_items) * len(labels) * len(ORDERS)`. If an item has a duplicate (extra) verdict, `valid > planned` for that item and `missing_verdicts` can be negative. `admit()` excludes the duplicate item from scoring, but `valid_verdicts`/`missing_verdicts` are reported in the sheet regardless.

**Failure scenario:** A judge writes two verdicts for one (item, order) by mistake; the sheet prints `missing_verdicts = -1`, which is nonsensical and undermines trust in the count.

**Proposed change:** Cap at 0: `missing_verdicts=max(0, planned - valid)`, or compute missing as `planned - sum(min(valid_by_item.get(it,0), len(labels)*len(ORDERS)) for it in s_items)`.

---

## What the frozen tests miss (summary beyond F3)

- No test asserts the frozen `wave1_identical` equals the value recomputed from the current B8 (only the A7 item set is re-verified in `compute_subjective`). A stale frozen `wave1_identical` would not be caught — though the `b8_sha256` guard makes this practically unreachable.
- No test exercises a duplicate verdict for an A7 item (the F4 negative-missing path).
- No test covers `a7-cursor`/`a7-seal` against a FROZEN.json whose `b8_sha256` differs from the sheet's B8 (only `test_b8_changed_since_freeze_refuses` covers the sheet side; the judge-side refusal on a stale B8 is symmetric but untested).

## Scope requests (not findings)

- S1: The candidate's `wave1_identity` refuses if any Wave 1 pair has non-identical keys. E3 doesn't ask for Wave 1 packets, but a future non-identical Wave 1 pair would need a packet type the contract doesn't define. The refusal is the only safe behavior today; flagging only so the operator knows the panel cannot absorb a future non-identical Wave 1 without a contract change.

## Hazards

- H1: `freeze` includes every file under `out_dir` in the frozen set (including `README_JUDGE.md` and any stray `.DS_Store`). A benign edit to `README_JUDGE.md` or removal of a `.DS_Store` would make `check_frozen` refuse. Not a correctness defect (fail-closed), but it can surprise an operator who touches a non-packet file.

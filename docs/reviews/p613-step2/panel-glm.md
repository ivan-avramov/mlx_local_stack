Based on my review of the candidate diff, the contract, the implementer's report, and the frozen tests, here are my findings.

## NOTHING OF SUBSTANCE

I traced the contract rules through the candidate code and cross-checked the frozen tests. The candidate correctly implements Wave 1 rules 1–4 and 7, the rule-6 cross-wave check, the `all` commands, byte-identical regeneration, and the step-1 `a7` preservation. The one "mismatch" the implementer flags (A4 per-draw range) is actually **not** a mismatch — the contract's erratum (2026-11-04) corrects the range to 1.528–1.656, which is exactly what the code produces; the implementer's report references pre-erratum text, but the code and the golden test (`test_golden_decode_ratio_points`) both match the corrected contract.

The items below are minor or scope notes, not blockers.

---

### Minor

**M1 — Rejected-key shape inconsistency in `_w1_keys`**
- Location: `benchmark/bench/p426_verify.py`, `_w1_keys` (around line 1000–1010 of the candidate).
- Severity: minor.
- Evidence: confirmed in source. For a **non-reasoning** seed mismatch, the rejected key is `[block, x]` (2 elements); for a **reasoning** request-seed mismatch, it is `[block, x, ro["seed"]]` (3 elements, where `ro["seed"]` is the wrong `sampler_seed`).
- Problem: the rejected-key shape differs by axis. The contract says "Key: A1/A2 (block, `id`, `sampler_seed`); A3 (block, `id`, `seed`); A4 (block, task `seed`, `sampler_seed`)" — i.e. the key always carries the seed. A consumer keying off `len(key)` or positional access would see different shapes for the same kind of rejection.
- Scenario: a downstream consumer iterates `keys_rejected` and unpacks `key` as `[block, id, seed]` for all kinds; for a non-reasoning seed mismatch it would get a 2-element list and misread the seed.
- Proposed change: make the non-reasoning rejected key `[block, x, ro["seed"]]` (or `[block, x, None]` if you want to signal "seed ambiguous"), matching the accepted-key shape. The frozen tests only check `rid in str(key)`, so they would still pass.

**M2 — Implementer's report carries a stale A4 claim**
- Location: `.p613-material/implementer-report.md`, "The A4 mismatch" section.
- Severity: minor (report only; the code is correct).
- Evidence: the report says "the contract says 1.584–1.656" and "I did not change the code to match." The committed contract (`docs/specs/p613-step2-con## NOTHING OF SUBSTANCE

I traced the contract rules through the candidate code and cross-checked the frozen tests. The candidate correctly implements Wave 1 rules 1–4 and 7, the rule-6 cross-wave check, the `all` commands, byte-identical regeneration, and step-1 `a7` preservation. The one "mismatch" the implementer flags (A4 per-draw range) is **not** a mismatch — the contract's erratum corrects the range to 1.528–1.656, which is exactly what the code produces; the implementer's report references pre-erratum text, but the code and the golden test both match the corrected contract.

The items below are minor or scope notes, not blockers.

---

### Minor

**M1 — Rejected-key shape inconsistency in `_w1_keys`**
- Location: `benchmark/bench/p426_verify.py`, `_w1_keys` (candidate lines ~1000–1010).
- Severity: minor.
- Evidence: confirmed in source. For a **non-reasoning** seed mismatch, the rejected key is `[block, x]` (2 elements); for a **reasoning** request-seed mismatch, it is `[block, x, ro["seed"]]` (3 elements). Accepted keys are always 3 elements (`[block, x, seed]`).
- Problem: the rejected-key shape differs by axis for the same kind of rejection. A consumer keying off `len(key)` or positional access would misread a non-reasoning rejection.
- Scenario: a downstream consumer unpacks `key` as `[block, id, seed]` for all kinds; a non-reasoning seed mismatch yields a 2-element list and the seed is misread.
- Proposed change: emit `[block, x, ro["seed"]]` for non-reasoning rejections too (the OFF seed is well-defined). The frozen tests only check `rid in str(key)`, so they still pass.

**M2 — Implementer's report carries a stale A4 claim**
- Location: `.p613-material/implementer-report.md`, "The A4 mismatch" section.
- Severity: minor (report only; the code is correct).
- Evidence: the report says "the contract says 1.584–1.656" and "I did not change the code to match." The committed contract (with the 2026-11-04 erratum) lists the full six draws including 1.528; the code produces 1.528–1.656; the golden test pins `min == 1.528`.
- Problem: the report's "caveat" is stale and could mislead the operator into thinking the code diverges from the contract, when it actually matches the corrected contract.
- Proposed change: correct the report (or note it's moot since the erratum landed).

---

### What the frozen tests miss

**G1 — `compute_all` with a rejected A7 session.** Every `compute_all` / `verify_all` test uses a clean A7 world (both s1/s2 accepted). The family recompute path where `a7["family"]["raw_p"]` has fewer than 2 A7 members (so `FAMILY_ORDER` yields m < 3 and the label becomes "INCOMPLETE: missing […]"), and the `if f"A7-{s}" in holm_p` skip in the holm_p overwrite, are not exercised. The code path is reasonable (label degrades to INCOMPLETE, rejected session keeps no holm_p), but a test would pin it. Not a code defect — a test gap.

**G2 — `compute_all` with a rejected Wave 1 pair that is also the only accepted block for an axis.** The `_speed` function's `_speed_inference` handles "one valid block → descriptive" and "no valid block", but the flags path (`for scope in V.W1_BLOCKS + ("both",)`) skips scopes with `rec.get("status") != "accepted"` only for the point/Holm flags; the acceptance flag path checks `d is None` but not `status`. A rejected pair yields `d = sp["blocks"].get(scope)` which is `None` for a rejected block (since `_speed` only populates `blocks` for accepted blocks via `per_block_keys`). So it's handled, but no test covers an axis with one rejected + one accepted block.

---

### Scope requests (beyond the contract, not defects)

**S1 — M1 `result.json` status check.** `_w1_receipt_reasons` adds `if kind == "m1" and m["result"].get("status") != "ok": reject`. The contract's rule 1 lists receipt validity, not `result.json` status. Reasonable conservative addition; flagged for operator awareness.

**S2 — A3 turn-2 draft check.** `_drafts` includes `turn2.draft` for vision, so rule 2d checks turn-2 draft state too. The contract says "OFF rows: every `draft` value null; ON rows: draft_kind == mtp …" — "every draft value" can be read to include turn 2. Reasonable, but it's an addition.

**S3 — Evidence-only fields in B8.** `log`, `speed_problems`, `gitlinks`, `entry_present` are recorded but never gate. The contract says "Also recorded (evidence, never a gate): entry_equal, globals_equal, closure_files" — the candidate adds a few more evidence fields. No consumer hazard; just broader than specified.

---

### Hazards checked and cleared

- **Absolute paths / non-determinism:** `cross_wave` uses `tempfile.TemporaryDirectory(prefix="p426-rule6-")` and extracts git archives there; only repo-relative paths enter the record. `test_record_is_json_and_has_no_absolute_path` and `test_outputs_have_no_absolute_path` confirm. No wall-clock in outputs.
- **Step-1 `a7` unchanged:** `compute_a7` wraps `_compute_a7_parts(...)[0]`; the `a7` CLI path is preserved; `test_a7_commands_are_unchanged` and `test_all_embeds_the_step1_a7_record` confirm byte-identical A7 embedding.
- **Input coverage:** `_check_all_b8` verifies the union covers each axis's inputs; `compute_all` re-checks Wave 1 inputs against `b8["inputs"]`; `_compute_a7_parts` checks A7 sub-record inputs against `results_root`. Noise-floor inputs are added to `signals["inputs"]` without B8 coverage — this is step-1 behavior, not a regression.
- **Deny-list:** `_w1_member` resolves and checks `DENY_PATTERNS`; `wave1.s2/` does not match the `wave1(/|$)` pattern (the `.` before `s2` saves it); smokes, archive, S-build `p426-{off,on}-*` all deny correctly.
- **Rule 6 closure:** union over both commits, computed on the committed tree (not the working tree), `git diff --name-only` at repo top. Cwd-independence and read-only tests confirm.

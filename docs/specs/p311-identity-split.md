# P311 — split the tg1 probe identity into generation and scoring (C164 approved; M64 spec §4; C166 build)

Problem: `tg1_runner.identity()` hashes generation code and scoring code into ONE `probe_code_sha256`
(`benchmark/bench/tg1_runner.py:319-342`). Every scoring fix (P299, C163, P309 this week) therefore orphans every
row for pairing and forced an ≈18 h re-baseline (C164).

## Change

1. **Three hashes in the manifest `runtime` and every row** (sha256 over relpath + NUL + bytes, as today):
   - `generation_code_sha256` — code that shapes what the model sees or how a run proceeds: `tg1_runner.py`,
     `token_turn_gate.py`, `structured_grade.py` (in-run grading drives the gate), `proc_guard.py`,
     `m62/universe_preflight.py`, `m62/replay.py`, `run_opencode_probe_v2.py`, `provenance.py`,
     `opencode_common.py`, `opencode_export.py`, `convergence.py`, `rowschema.py`, `paths.py`, `model_params.py`,
     `quant_info.py`, and NEW `bench/deny_rules.py`.
   - `scoring_code_sha256` — code that labels or scores recorded evidence: `answer_key.py`, `web_audit.py`,
     `web_audit_prompt.md`, `web_audit_cursor.py`, `legacy_audit_records.json`.
   - `probe_code_sha256` — UNCHANGED definition (all of the above, today's module list), kept for continuity with
     every existing row, pin and report.
2. **Carve-out:** `answer_key.shell_deny_patterns` (it builds the carrier's shell deny rules — generation-relevant) moves
   to `bench/deny_rules.py`; `answer_key` re-exports it so callers and tests keep working. `answer_key.contact()` stays
   in `answer_key` (scoring): it runs in-probe to set the row's `answer_key_contact` / `answer_key_evidence`, and the row
   records `scoring_code_sha256` so the version that produced the flags is known. `deny_patterns_for` (driver-side,
   builds an extra-deny list whose file sha is already in `runtime.selection`) stays in `answer_key`.
3. **Pairing:** the chain runner pins and verifies `generation_code_sha256` (new `--generation-code-sha`, required for
   `chain`); `probe_code_sha256` and `scoring_code_sha256` are recorded, not pinned, so a scoring-only change between
   legs no longer aborts a chain. `--probe-code-sha` stays accepted for one release (if given it is still verified,
   preserving today's behaviour for anyone who passes it).
4. **Reporting:** report scripts print the `scoring_code_sha256` they ran with and pair rows on
   `generation_code_sha256` when both rows have it, falling back to `probe_code_sha256` for older rows.
5. **Identity CLI:** `--print-identity` prints all three hashes.

## Tests (red first)
- The three module lists are exact and disjoint where intended (`generation` ∩ `scoring` = ∅;
  `probe` = today's list, byte-identical value on an unchanged tree).
- A scoring-only change (temporarily edit `web_audit_prompt.md` or `answer_key.py` in a temp copy) leaves
  `generation_code_sha256` unchanged and changes `scoring_code_sha256` and `probe_code_sha256`; a generation change
  changes `generation_code_sha256`.
- `deny_rules.shell_deny_patterns` == the old `answer_key.shell_deny_patterns` on the existing deny fixtures; the
  carrier bytes the probe writes are unchanged.
- Chain runner: generation drift between legs → refused; scoring-only drift → accepted and recorded.
- Fake probe emits the three fields.

## Out of scope
Report-time re-derivation of `answer_key_contact` from stored evidence (possible later: the evidence and the corpus are
retained); the M64 arm identities (they reuse this split per arm).

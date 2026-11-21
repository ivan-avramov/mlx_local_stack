# M76 B4b-2 — change review round 1 of 3 (panel verify of candidate 1): ledger

Candidate 1 = `fe-b4b2/out/candidate-1.patch` (11 files, +2684 / −100) on baseline `26287dce2` (spec v1.5). Panel: GPT-5.6 Sol High,
GLM 5.2 High (cursor-agent, checkout, user instructions unconfirmed), Claude Sonnet 5.5 (fresh `claude -p`, `e8254c70…`; shares the
test-writer's model). Judged by the designer, intent first (S28-P5).

| id | finding (raised by) | disposition | why |
|---|---|---|---|
| B1 | `verify_a8_kv` requires `base_b8_sha256`; spec §3.2 and every frozen test call `verify_a8_kv(results_root)` (Sol P1, GLM F1) | adopted | the spec's interface; derive the base sha from `<results_root>/B8.json` (fail-closed when absent), explicit value a seam. |
| B2 | Slot inventory hand-rolled (`_a8_slots`, `_a8_session_rows` globbing every JSONL, `load_dnf` dropping a DNF beside a row, harness-DNF record not seal / field-equal to its sidecar, no reason check) (Sol P2, Sonnet P4, GLM) | adopted | one inventory authority: `chain_rows.load_slots` / `validate_progress` / `_harness_dnf_rows`, plus exact chain-record ↔ sidecar equality; the extra checks the spec needs (two accepted attempts refuse) on top. |
| B3 | Orphan exemption = seen run ids × discarded items (Cartesian), not the discarded attempt's own (item, run id) (Sol P3, Sonnet P3) | adopted | bind per slot from the attempt / invocation records. |
| B4 | Legs not bound to the full v8 identity (draw / universe / image pins, model, generation identity, probe code, scaffold policy) (Sol P4) | adopted | data validity: one v8-binding validator per attempt. |
| B5 | Accounting status from an OR of markers; row marker ignored; disagreement / orphan sidecar not refused; no runaway-tax exclusion; the leg not marked speed-invalid (Sol P5, Sonnet P5) | adopted | §9.4 / §9.6: exact agreement (slot state, ledger, row, sidecar), orphan sidecar refuses, excluded from decode / walls / tax, leg speed descriptive-invalid. |
| B6 | `B8.json` not written when B8-A8 refuses (Sonnet P1) | adopted | §3.5 / L2: write `B8.json` first, then B8-A8 (refusal → rc 2, `B8.json` stays). |
| B7 | Latency windows parsed as local time (Sonnet P2); latency rows not validated numerically (Sol P7) | adopted | parse ISO-Z as UTC; validate t / ms / CPU finite, non-negative. |
| B8 | tg1 golden allow-list wildcards every `.b8.inputs.*.jsonl` sha (Sol P8, Sonnet) | adopted | pin the exact changed paths. |
| B9 | Top-level `status: complete` with a rejected confirmatory session (Sol P9, GLM) | adopted | complete only when every confirmatory session is accepted. |
| B10 | Row `sampler_seed` not bound to the plan's session seed (Sonnet P6, scope request) | adopted (designer, under C379's run-as-efficient; shown to the operator) | data validity, one REASON: `rowschema.sample_seed(id, 0, TG2_P426_LEGS[session].seed)`. |
| B11 | Real packet / export acceptance (§7.3) unverified on real bytes (Sol P6, Sonnet P7, GLM F5) | covered (designer) | runs on the new-identity pilot pair once harvested, before the panel freeze; regrade only. |
| B12 | The frozen suite does not exercise `_a8_packet` / `kv_export` (GLM F4) | adopted (test-writer) | the signatures now exist; scenario tests in delivery 3. |
| B13 | `_sequence_*` gained a message-only `namespace` parameter (GLM F2); extra B8-A8 keys (GLM F3) | declined | no behaviour change; the extra keys bind the draw (`repo_inputs`) and are descriptive. |

## Test-writer delivery 2 (same round; 140 / 140 amended tests pass on candidate 1; "fix then merge")

| id | finding | disposition | why |
|---|---|---|---|
| B14 | `check_b8_a8` re-hashes `repo_inputs` at `rows_root.parents[1]` (layout assumption) (m2) | adopted | pass the repo root explicitly; the refusal names the missing input. |
| B15 | `v8.arms` reason unreachable: `a8_applies` already requires `TG2_PAIR` (m3) | adopted | keep one place: `a8_applies` decides applicability by corpus / lever, the arms mismatch is a REASON on the record. |
| B16 | `b8_a8_sha256 or _sha_doc(...)` falls back to a canonical-JSON sha, not the file's bytes (m5) | adopted | the file sha everywhere (header, panel freeze); no fallback. |
| — | M1 = B8; m1 = B6; m4 = B9; n1 = B2 | merged | |

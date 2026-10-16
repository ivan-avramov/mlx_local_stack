# P311 — split the tg1 probe identity into generation, decision and scoring (C164 approved; M64 spec §4; C166 build)

v2 2026-10-16: applies Cursor `gpt-5.6-sol-high` round 1 P1–P9
(`benchmark/chains/c147/reviews/p311/round1.cursor-gpt-5.6-sol-high.md`). v1 = `ed9a4030`.

Problem: `tg1_runner.identity()` hashes generation code and scoring code into ONE `probe_code_sha256`
(`benchmark/bench/tg1_runner.py:319-342`). Every scoring fix (P299, C163, P309) therefore orphans every row for pairing
and forced an ≈18 h re-baseline (C164).

Scope: the tg1 scaffold (`opencode-v2-web-tg1`) only. The standard v2 identity (`run_opencode_probe_v2.py:603-613`,
basename + bytes over six modules) and every frozen probe are unchanged (P3).

## 1. Code hashes (sha256 over relpath + NUL + bytes, the tg1 recipe)

| Hash | Pinned? | Modules |
|---|---|---|
| `generation_code_sha256` | pinned (chain, resume) | `bench/tg1_runner.py`, `bench/token_turn_gate.py`, `bench/structured_grade.py`, `bench/proc_guard.py`, `m62/universe_preflight.py`, `m62/replay.py`, `run_opencode_probe_v2.py`, `bench/provenance.py`, `bench/opencode_common.py`, `bench/opencode_export.py`, `bench/progress_gate.py` (P2), `bench/convergence.py`, `bench/rowschema.py`, `bench/paths.py`, NEW `bench/deny_rules.py`, NEW `bench/rerun_policy.py` |
| `scoring_code_sha256` | recorded per row | `bench/answer_key.py`, `web_audit.py`, `web_audit_prompt.md`, `web_audit_cursor.py`, `legacy_audit_records.json` |
| `support_code_sha256` | recorded | `bench/model_params.py`, `bench/quant_info.py` (observational on tg1: the carrier sets sampling; `provenance.gather` only records `params_for`; quant inspection never blocks — P2). Build check: if either module is reached on a tg1 path that changes the carrier, a request or a refusal, it moves to generation. |
| `probe_code_sha256` | recorded (legacy) | union of the three lists; same field, same recipe. Its VALUE changes once at this build (new modules, edited `answer_key.py`) — P3. |

Lists are exact and pairwise disjoint.

## 2. Decisions computed from scoring code (P1, P8)

In-probe decisions that change which attempts run or under which deny rules — `answer_key.audit_states` /
`require_audits` / `rerun_plan` as used by `_rerun_resume`, and `answer_key.contact()` (row flags) — are split:

- `bench/rerun_policy.py` (generation): rerun eligibility, `done` set construction and deny planning (moved from
  `answer_key` / `_rerun_resume`; `answer_key` re-exports for callers).
- `bench/deny_rules.py` (generation): `shell_deny_patterns` (builds the carrier's shell deny rules).
- Audit verdicts and contact labels stay scoring.

**Decision freezing.** Every decision that consumes a scoring verdict is persisted, immutably, before the attempt it
gates: a rerun row records `rerun_decision = {superseded session_id, cheat basis (audit record keys), extra_deny,
scoring_code_sha256 at decision}`; every row records its own `scoring_code_sha256` and the `answer_key_contact` /
`answer_key_evidence` computed with it. On resume the probe recomputes each persisted decision with the current
scoring code; a recomputed decision that differs refuses (`REFUSED: decision drift — operator re-decides`); it never
silently changes the attempt set or deny rules. Contact is owned by the probe (row time). M64 adopts this rule for its
chain-level contact/rerun (§9): the decision is frozen when the rerun launches (M64 spec amendment at M64 build).

Reports that re-derive labels print both the row-time and the report-time `scoring_code_sha256`.

## 3. Pairing identity (P5)

`generation_identity_sha256` = sha256 of canonical JSON (sorted keys) of: `generation_code_sha256`,
`scaffold_policy_sha256` (gate, hygiene, plugins, carrier, universe, env, grader), `opencode_version`,
`opencode_exe_sha256`, `opencode_bench_config_sha256`, `carrier_source_sha256`, `agent_system_sha256`, `polyglot_sha`,
`sampling_profile`, `draft_kind`, `serving_path`. Recorded in the manifest `runtime` and every row. Model, lang and
seed schedule are compared separately (pairs are per model × item × seed). Reports pair on this composite; the code
hash is one component. M64 extends it per arm (adapter + client snapshot).

## 4. Chain, resume and barrier (P4, P7)

- The probe's resume compares generation identity fields only (not every `identity()` field); rows of one leg may
  carry different `scoring_code_sha256` (mixed segments allowed, each row stamped).
- The runner pins `generation_code_sha256` and `generation_identity_sha256` at the first manifest; scoring/support
  hashes are recorded in `chain.json`, not pinned. Scoring drift between pilot and full, or between legs, is accepted
  and recorded; generation drift aborts.
- CLI transition matrix: `--generation-code-sha` only → new mode; `--probe-code-sha` only → legacy strict mode (pins
  the union hash, as today) with a warning; both → both verified; neither → refused. `drive_chain.sh`,
  `launch_tg1.sh` usage, the c147 README and the handoff are updated.
- `RUNTIME_PINNED`, `SHA_FIELDS`, `validate_leg`, `malformed_identity` and `fake_probe` learn the new fields; absent or
  malformed values fail closed in new mode.

## 5. Historical rows (P6)

Existing rows carry none of the new hashes. A reviewed sidecar `benchmark/results/identity_migration.json` assigns
`generation_code_sha256` / `generation_identity_sha256` to historical manifests (P223, M63, c144-base, M65 pilot):
computed at the manifest's `git.stack_head` with the v2 lists, accepted only when the legacy `probe_code_sha256`
recomputed at that commit with the old list equals the recorded value (proves the tree matched the commit); otherwise
the leg is `generation_identity: unavailable` and old-to-new pairing is refused for it. Reports load the leg manifest
(plus the sidecar) and refuse mismatched composite identities. The P223/M63/c144-base report numbers must not change.

## 6. Identity CLI

`--print-identity` prints all four code hashes and `generation_identity_sha256`.

## Tests (red first) — P9

1. Lists exact and disjoint; golden vectors for `generation_code_sha256` and the legacy recipe on a fixed temp tree.
2. Scoring-only edit (temp copy of `web_audit_prompt.md` / `answer_key.py`) → generation hashes unchanged, scoring and
   probe hashes changed; generation edit → generation hashes changed; support-only edit → only support/probe changed.
3. Composite: changing each listed field changes `generation_identity_sha256`; model/seed do not.
4. `deny_rules.shell_deny_patterns` == old function on the deny fixtures; carrier bytes unchanged.
5. `rerun_policy` == old `_rerun_resume` decisions on recorded fixtures; decision drift on resume → refused; a rerun row
   carries `rerun_decision`.
6. Resume: scoring drift between pilot and full in one rows file → accepted, rows stamped per segment; generation drift →
   refused.
7. Chain runner: CLI transition matrix; generation drift between legs aborts; scoring drift accepted and recorded;
   malformed/missing new fields in `RUNTIME_PINNED` / `SHA_FIELDS` / `validate_leg` / fake probe fail closed.
8. Migration: sidecar entries verify (legacy hash recomputed at `stack_head`); a mismatching commit → unavailable;
   report refuses old-to-new pairing without a verified entry; P223/M63/c144-base report outputs byte-identical.
9. Standard v2 identity unchanged (golden value on an unchanged tree).

## Out of scope
Report-time re-derivation of `answer_key_contact` from stored evidence; the M64 arm identities (they reuse §3 per arm);
the standard v2 and frozen probes.

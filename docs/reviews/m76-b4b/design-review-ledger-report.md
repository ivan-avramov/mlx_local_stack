# M76 B4b — design review ledger (four-eyes STRICT, opinion; round 1 of 3), 2026-11-15

Spec `docs/specs/m76-b4b-tg2-runner.md` v1.1 draft (`6c252779`). Panel, read-only `checkout` snapshot (rule files renamed):
Sol cursor-agent `gpt-5.6-sol-high` (14 findings; user instructions unconfirmed), GLM cursor-agent `glm-5.2-high` (17 + 3 scope
requests + 7 test gaps; unconfirmed), Claude Sonnet `claude -p` (`claude-sonnet-5-5`, session `4d975807`, `--setting-sources ""`; 15
+ 1 scope request). Raw: `opinion-design-{sol,glm,sonnet}.md`. Every finding below was traced by its raiser in the source; the designer
re-traced D1 (make-up refused by the signals: `p426_signals._check_makeup`), D7 (`kv_axis_verdict` drops `languages`).

Verdict: the spec is not dispatchable — it names the destinations but leaves most seams to the implementer. All findings are original
(spec v1); none is a repair. Dispositions:

| id | raised by | finding | sev | disposition |
|---|---|---|---|---|
| D1 | Sol P12, Sonnet F11, GLM B17 | "make-up as tg1" (C345 Q1): tg1's signals refuse any make-up leg; make-up rows are never substituted; a make-up leg cannot change A8 (DNF = 0) but costs hours | blocker | → operator (reopen C345 Q1; rec: no tg2 make-up) |
| D2 | Sol P6, Sonnet F10, GLM B6 | C331 (3) "stricter α" is unrealisable (A8 α* 0.001 = the grid's floor; `axis_verdict` takes no α); k = 1 screen cannot estimate κ | blocker | → operator (rec: re-check is a stop-for-operator gate, α stays 0.001) |
| D3 | Sonnet (could drop) | the screen re-runs decider s1's first 40 items at the same seed (≈ 3–4 GPU h / arm) | — | → operator (S24-P11) |
| D4 | Sol P14, Sonnet scope, GLM | the A8 panel packet (cert §7) / "pending subjective review" label not addressed | scope | → operator |
| D5 | Sol P1, GLM B9, B10, Sonnet F7 | `Tg2Corpus` misses abstract methods; mapping: `GradeOutcome.outcome` always `"model"`, `failing = result.failing(leaves)` (out-of-universe failures count), phases args, `timeout_s` / `prepared_cargo_toml` / `solutions` from the entry, `storage_cap` sets no resource flag | blocker | adopted (v2: full contract) |
| D6 | Sol P2, Sonnet F2, F3 | schedule: `tg2_tier` emits all sessions as `sessions[].cells[]`, consumers read `blocks[].legs[].invocations[]`; per-leg projection, session dir names (`screen` vs `s1`), seeds, language order, item order; reload = 5 items PER LANGUAGE (M65 v5, settled) | blocker | adopted (v2: one per-leg table) |
| D7 | Sonnet F1, GLM B2 | `ChainConfig` allows `p426_continue` only for `tg1-p426` / builder `tg1`; non-tg1 builders call `ensure_overlay` (aborts under mtp) and use M64's `PRED_S`; chain `needs_docker` default | blocker | adopted |
| D8 | Sol P3, Sonnet F4 | tg1 scaffold hard-coded in `chain_ops.validate_leg`, A4 gate (`session_pinning_gate`), `structured_grade.validate_reports` (rejects valid tg2 outcomes), configgen carrier target; files outside scope | blocker | adopted (scope widened) |
| D9 | Sol P4, Sonnet F6, GLM B1, B3 | freeze / amendment / pilot gate tg1-shaped (R1–R3 rehearsals, `PILOT_N` 5, `w_python_s` / `w_go_s`, `ITEM_COUNT`); smoke deadline circular; heavy-tail number unsourced | blocker | adopted (v2: tg2 rehearsal policy, numeric walls, amendment schema) |
| D10 | Sol P7, Sonnet F5, GLM B5, B12, B13 | `wave2-tg2` refused by `NAMESPACE_RE`; B8 hard-codes `wave2`, deny-lists `smoke`; `verify_all_kv` discovers A7 only; no `kv_a8_sessions()` | blocker | adopted (`wave2.tg2`, parameterised readers) |
| D11 | Sol P8 | B8's `_leg_reasons` accepts only `VALID`; `VALID_WITH_DNF` A8 legs would be rejected | blocker | adopted |
| D12 | Sol P9, Sonnet F9, GLM B4, B16 | A8 HOLD not surfaced: `kv_flags` / `render_kv` omit A8, `kv_axis_verdict` drops `languages`; A8 noise floor (cert §8) | major | adopted |
| D13 | Sonnet F8 | grade-join timeout `2 × max(grader_timeout_s) + 60` too short for multi-step tg2 grades (8 h leg lost); default universe is tg1's | major | adopted |
| D14 | Sol P10, GLM B7, B15, Sonnet F12 | injected positives: tg2 inject addenda, item / seed / arm, out root, predicates, verifier (`m62/inject_verify` tg1-only) | major | adopted (pre-registered table) |
| D15 | Sol P5, Sonnet F12 | draw / universe sha pinned independently (L6) | major | adopted |
| D16 | Sol P11, Sonnet F14 | "tg1 byte-identical" impossible for closure-derived identity fields | major | adopted (boundary defined; tg1 identities rotate, C178) |
| D17 | Sonnet F12 | chain entry / argv per leg kind / draw seam / corpus-root seam left to the implementer | major | adopted (named) |
| D18 | Sol P13, Sonnet F13, GLM B8 | harvest: closed artifact → destination table, exact unmatched names | minor | adopted |
| D19 | GLM B11 | positives corpus root via private helper | major | adopted (with D17) |
| D20 | GLM B14 | `arm_runner` refusal text tg1-specific | minor | adopted |
| D21 | all | acceptance misses chain start, validation, schedule readers, join bound, HOLD in flags / render, public B8 / signals CLI over harvested output, freeze round-trip | minor | adopted |

Next: operator calls D1–D4 (S24-P10 … P13), then spec v2 with every adopted finding, then a round-2 design review (verify) of v2.

## Round 2 of 3 (verify of v2, `b81e51b5`), 2026-11-15

Sol (fresh session, cursor-agent cannot resume), GLM (fresh), Claude Sonnet (resumed `4d975807`). Raw: `verify-design-{sol,glm,sonnet}.md`.
Round 1: D1, D3, D6, D7, D8, D10, D11, D13, D15, D16, D19, D20 resolved (all three); D2, D4, D5, D9, D14, D17, D18, D21 partly. New
(all original to v2's new text or left open by it; designer agrees with each on its trace):

| id | raised by | finding | sev |
|---|---|---|---|
| E1 | Sol P1 | the tg1 prompt points at `.docs/instructions.md`, which tg2 materialisation excludes — the task text must be inlined from the pinned source | blocker |
| E2 | Sol P2, Sonnet N2 | `--leg` has no mapping to the shared core's `mode` / sessions / record kind; rehearsal / inject argv missing | blocker |
| E3 | Sol P3, Sonnet N1, N2, GLM F6 | tg2 R2 / R3 not runnable: injection hooks Python / Go-only (`p426_hooks.py` out of scope), `cmd_v8` needs R1, `settle_bound_s` from R1, rehearsal manifest step missing | blocker |
| E4 | Sol P5, Sonnet N6 | `m76_sim.recheck(out=)` is a directory (writes `recheck-A8.json`); no sealed ack; harvest / B8 location unstated | blocker |
| E5 | Sol P6, Sonnet N5, GLM F4 | A8 panel "as A7" impossible: singular `solution` / `test`, raw polyglot start tree (shows grader rewrites as edits), single-file diff, A7-keyed member functions | blocker |
| E6 | Sol P8, Sonnet N4 | the positives have no sealed record and no consumer; X not stated | major |
| E7 | Sol P4 | grade call: `prepared`, `extra_crates=()`, `guard` | major |
| E8 | Sol P7 | final tree must hold every grader-permitted mutable file (helpers, `Cargo.toml`) | major |
| E9 | Sol P9 | no blocking `a8_incomplete` flag | major |
| E10 | Sol P10 | the sensitivity must compare the whole blocking state (class, HOLD languages, interaction) | major |
| E11 | Sonnet N3 | `_sequence_leg_reasons` also rejects `VALID_WITH_DNF` | major |
| E12 | GLM F1, F2 | builder `tg2_p426`: `freezes_schedule` / `verify_schedule` keys and the `plan_*` reader; one schedule leg per (session, language) not stated | major |
| E13 | Sol P11 | harvest `<tag>` grammar open — exact regex / shared classifier | minor |
| E14 | Sonnet N7 | `chain_ops.t_coop` uses tg1's grader timeout table | minor |

Designer reading: the remaining defects cluster in two places — the rehearsal / freeze path (E2, E3, E6) and the post-harvest
consumers (E4's B8 side, E5, E9, E10, E11). The post-harvest consumers read harvested evidence and are regradeable (AGENTS.md:
regrade, not rerun). Proposal to the operator: S24-P14.

## Round 3 of 3 (final verify of B4b-1 v3, `63b0b573`), 2026-11-15

Sol (fresh), GLM (fresh), Claude Sonnet (resumed `4d975807`). Raw: `verify3-design-{sol,glm,sonnet}.md`. Resolved (all three): D1, D3, D6,
D8, D13, D15, D16, D18 (intent), D20, E7, E8, E12–E14 (intent). Open (each confirmed by its raiser's trace; designer agrees):

| id | raised by | finding | sev |
|---|---|---|---|
| G1 | Sonnet G1 | the core's snapshot lives under `grading-private`; `tg2_grade._disjoint` aborts every grade → snapshot outside `private` | blocker |
| G2 | Sol P2 | `source_root(lang)` is `<root>/<lang>/exercises/practice` by contract; `exercise_dir(source_root…)` doubles the path | blocker |
| G3 | Sol P3 | the core sends `--evidence p426` only for `tg1-p426` → tg2 legs lose the item barrier / reconciliation | blocker |
| G4 | Sol P4, Sonnet G5, GLM R1, R2 | rehearsals: `--rehearsal` → `inject` values unmapped; `p426_inject_stall` Python-only; `p426_freeze rehearsal` needs the pair + both worktrees + date; v8 refuses an N16-only manifest; R3 settle bound when the killed item has no record | blocker |
| G5 | Sol P7, Sonnet G3 | re-check records lack a self-hash → `publish_run_files` refuses; ack must be the sealed record's `sha256`; publication path is `publish_run_files`, not `classify` | blocker |
| G6 | Sonnet G2, GLM R4 | `TG2_BOOKKEEPING_RE` misses `ls-<volume>`, `<step>-n-x`, uppercase `T` in run ids | major |
| G7 | Sonnet G4 | positives launch: router / A4 / worker load, frozen prompt date source, probe CLI inputs | major |
| G8 | Sol P6 | v8 must compare the positives record's identities (N16 commit, generation / scaffold, universe, draw, image) to its live inputs | major |
| G9 | Sol P5 | grade call: `snap.path` (not `work`), the `snap is None` branch | major |
| G10 | GLM R6, R8 | `ChainConfig.__post_init__` and `chain_core.plan` / `verify_schedule` dispatch for builder `tg2_p426` named but not specified | major |
| G11 | GLM R3, R7, R10 | `pilot_gate_problems` (name, n), sequencer re-check hooks / `Stop(5)` / `--recheck-ack` flag, `KV_DOSSIER_PAIRS` per corpus — named, not wired | major |
| G12 | GLM R5 | `validate_reports` exact-name artifacts vs `junit-NNN.xml` | major |
| G13 | Sol P8 | prompt forbids build-file edits the grader allows (`Cargo.toml`) | minor |
| G14 | Sonnet G6 | `{H}` strings not exact literals | minor |
| G15 | Sonnet G7 | final-tree enumerator: complement of `tamper_reasons` | minor |
| G16 | GLM R9 | refusal text / inject out-root — already in v3 §1 (designer: resolved; GLM missed it) | — declined |

Pattern: round 3's findings are call-site facts (a private helper's precondition, a regex vs real names, a CLI's required flags) a
red-first implementer meets on the real path. Review budget exhausted → the operator (S24-P16).

## Round 4 (goal-anchored, operator-granted C348; v4 `8f9af2a0` → v5), 2026-11-15

Sol (fresh), GLM (fresh: NOTHING OF SUBSTANCE), Claude Sonnet (resumed `4d975807`: no goal failure; two minors). Raw:
`r4-design-{sol,glm,sonnet}.md`. Converged.

| id | raised by | finding | sev | disposition |
|---|---|---|---|---|
| H1 | Sol P1 | the outcome mapping omits `output_cap` (a scored model outcome) → a 16 MB output would invalidate a leg | major | adopted |
| H2 | Sol P2 | an agent's own `cargo test` creates `target/` / a lock → false tamper, broken snapshot, lost evidence; one normalised view | major | adopted (behaviour + a real-path test) |
| H3 | Sol P3, Sonnet F1 | R2 / R3 "each arm" = four rehearsals, v8 reads two → R2 on X, R3 on N16 (tg1's assignment) | major | adopted |
| H4 | Sonnet F2 | which seams may be faked | minor | adopted (router, worker, agent, docker only) |
| H5 | Sol P5 | the bookkeeping-tag regex duplicates the grader's private grammar → availability risk; the grade-sequence directory is the boundary | minor (over-engineering) | adopted |
| H6 | Sol P4 | reuse tg1's carrier under the tg2 label | minor (over-engineering) | declined — the carrier is generation data in the probe identity; one generated target is cheap and keeps tg2's provenance its own |
| H7 | Sonnet (over-eng.) | 12 injected positives → 3 (one language) | — | declined — M65 v5 (settled) asks one item per language; ≈ 30 GPU min |
| H8 | Sonnet (over-eng.) | positives identity: sha pin + N16 commit only | — | declined — the field comparison is what catches a record from a rotated harness identity (round 3 G8) |
| H9 | Sonnet (over-eng.) | drop the R2 / R3 GPU legs for red tests | — | declined — the tg2 probe / chain path is new; two one-item legs (≈ 15 GPU min) prove it on the real box |

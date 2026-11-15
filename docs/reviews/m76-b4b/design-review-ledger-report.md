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

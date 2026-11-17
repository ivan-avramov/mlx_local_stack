# M76 B8 kv planned kinds — change review ledger (four-eyes light, opinion; round 1 of 3), 2026-11-16

Candidate 1 (implementer Claude Opus `claude -p`, session `59a1797e`) on `3c199587`; spec `docs/specs/m76-b8-kv-planned-kinds.md` v1.
Test-writer Claude Sonnet (session `0338a205`, continued): 47 tests frozen 2026-11-17T01:35:06Z, delivery 2 verdict fix-then-merge.
Panel: Sol `gpt-5.6-sol-high` (ran B8 on the real harvest), GLM `glm-5.2-high` (traced; could not execute). Designer reproduced Sol's
P1 and P4 on the candidate over the real harvested stage-3a Wave 1 (`$STACK_WORKDIR/m76/s24-p7-check/cand/B8.json`): 4 / 10 pairs
accepted (Math500, cjudge); vision, reasoning, longctx rejected.

| id | raised by | finding | sev | disposition |
|---|---|---|---|---|
| K1 | implementer, test-writer, GLM F1, Sol P5 | `test_m76_b3_impl_wave1::test_main_kv_refuses_v…` relied on the old default (with `m1`) | major | adopted: pass `--axes m1` in its `n16,x` half |
| K2 | Sol P2 | explicit `kinds=` (e.g. `()`) yields a successful B8 with zero pairs — an incomplete planned wave passes the API | major | adopted: `verify_all_kv` always verifies the planned kinds; subsets only in the lower-level helper |
| K3 | Sol P3, GLM F2 | `compute_kv` ignores `dropped` (M1 "missing") and emits NO blocking flag with 6 planned pairs rejected | major | → operator (spec scope: `p426_signals.py` read-only) — S24-P23 |
| K4 | GLM F3 | no test runs the signals over the new record | minor | adopted with K3 |
| K5 | GLM F4, test-writer R1 | `dropped` only under `kinds=None` un-locked | minor | adopted (moot after K2) |
| K6 | test-writer R3 | `p426_plan` imports the kind list from `p426_verify` (layering inverted) | minor | adopted: the list lives in `p426_plan` |
| K7 | Sol P1 (reproduced) | B8 rule 2d compares per-arm facts across arms: vision's arm-local corpus path; reasoning / longctx result file names and hashes → 6 / 10 valid pairs rejected | major | → operator (pre-existing B3 defect, outside the spec) — S24-P23 |
| K8 | Sol P4 (reproduced) | every A5 row served `prompt_tokens` 130,776 vs `ids.json` frozen 129,130 (both arms, all 72 keys); the budget guard correctly keeps A5 incomplete | major (scope request) | → operator — S24-P24 |

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

## Fix round 1 (spec v1.1 + erratum v1.1a; C355 (2)(3), C356 (1)) and fix round 2

Fresh implementer Claude Opus (session `72383b75`) on candidate 1: F1–F5 (F4 adapted by erratum v1.1a: `verify_all_kv` keeps `kinds=`,
F2 closes K2 at the consumer), F3's ids.json regenerated (131,072 reasoning 130,776 = served; 196,608 budgets as served; diff confined incl. the
derived `prompt_deviation`). Test-writer delivery 3 (session `0338a205`): K1 and the 11 F3 tests amended (designer-authorised), 28 new tests,
214 pass; found R1. Fix round 2: R1 adopted (reasoning / longctx manifests must carry both result stamps per arm; all 76 harvested A4 / A5
manifests do). Designer merge amendments: the A5 fixtures in `test_m76_b3_impl_verify.World.leg` and the test-writer's s3 fixture stamp their
manifests as the runners do. Designer real-data acceptance (`designer-acceptance-report.md`): 10 / 10 planned pairs, 0 flags; a removed leg
refuses; a flipped result byte is rejected and flagged `wave1_incomplete`.

| id | raised by | finding | sev | disposition |
|---|---|---|---|---|
| R1 | test-writer delivery 3 | per-arm result integrity skipped when NEITHER arm is stamped | major | adopted (fix round 2) |
| D1–D4 | implementer | stamps only where written; two template kwargs; prompt_deviation in the diff; build from `frozen.path` | — | accepted (D3 → erratum v1.1a) |

## Round 2 of 3 (verify of candidate 3, fresh Sol + GLM; `verify-change-{sol,glm}.md`)

Sol: NOTHING OF SUBSTANCE. GLM: K1–K8, F1–F5, R1 resolved; no blocker / major. GLM A (the full regression with the amendments unrun) →
the designer's 37-file rerun; GLM B (a subset record's `not_run` omits M1; `dropped` is right) declined — subset records exist only in
fixtures and the consumer reads `dropped`; GLM C (a truncated reason list) declined, cosmetic.

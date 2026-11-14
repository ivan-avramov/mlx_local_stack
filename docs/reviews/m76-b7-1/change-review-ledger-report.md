# M76 B7.1 — joint plan and pre-registered follow-up looks (+ the C339 registration, folding B7.2) — four-eyes light — ledger

Spec `docs/specs/m76-b7-1-joint-plan.md` v1 → v1.4 (v1.1 change-review dispositions; v1.2 two A8 options; v1.3 C338 + verify
dispositions; v1.4 C339 registration). Baseline stack `4120d3c8` (contains the accepted B7). Copies `$STACK_WORKDIR/fe-m76b71/`.

## Cast

- Designer: Claude Opus 5.5 (this session).
- Implementer: Claude Opus via `claude -p` — candidate `fa19996d`; fix rounds `499d3c77`, `f655ee9f`, `78d2648a`, `08e4d7b6` (fresh each).
- Test-writer: Claude Sonnet via `claude -p`, one session continued (`493be4f1`): delivery 1 frozen before the candidate was revealed;
  deliveries 2–5 (verdicts: d2 static fix-then-merge → run after the designer applied the candidate; d3, d4, d5 merge).
- Panel: GPT-5.6 Sol High and GLM 5.2 High, `cursor-agent --mode ask`, read-only snapshot, user instructions unconfirmed; opinion on
  candidate 1; verify (fresh sessions, briefed with the opinion) on fix round 2.
- Shared: implementer, test-writer and designer are Anthropic; the panel is two other vendors.

## Rulings during the run

C338 (tg2 decider always runs, TD), C339 (A5-2L adopted; A7-5S not; HOLD any language < −20 pp; T1–T3 retired).

## Findings

| # | raised by | finding | disposition |
|---|---|---|---|
| 1 | implementer (candidate 1) | A7-2L's look 1 cannot meet the O'Brien–Fleming spend at any α (point-estimate condition independent of α) | confirmed by GLM and the test-writer; variant reported unavailable |
| 2 | test-writer d2, GLM F3 | the "both looks safe" A7-2L branch aborts the build | adopted (fix 1): records available + unsimulated flag |
| 3 | test-writer d2, GLM F4 | direct-vs-product consistency check not fail-closed | adopted (fix 1) |
| 4 | test-writer d2, GLM F5 | `b71=True` default | adopted (fix 1) |
| 5 | Sol P1 | screen and decider modelled independent; they are nested | adopted (fix 1) |
| 6 | Sol P2 | A5 per-task point gates omitted from clean PASS | adopted (fix 1); headline 54.6 → 49.1 % (T0) |
| 7 | Sol P3 | A8 large-harm HOLD absent; no threshold pre-registered | adapted: reported at three thresholds → operator (S23-P63) → C339 −20 pp |
| 8 | Sol P4 | GPU hours exclude mandatory work | adopted (whole-stage column) |
| 9 | GLM F1 / F2 | headline and A5-2L at the non-realisable A7 cell | adopted (realisable cell headline, both cells reported) |
| 10 | designer (S23-P68, side-agent note) | the A8 path misses a true 10 pp tg2 loss ≈ 17.5 % (screen) | v1.2 options T3 / TD → operator → C338 (TD) |
| 11 | Sol verify P12 | the report kept T0 as the committed plan after C338 | adopted (fix 3) |
| 12 | Sol verify P13 | A7-5S's clean PASS omits the unsimulated five-session flag | adopted (fix 3): no estimate shown |
| 13 | Sol verify P14 | "worst final look" unqualified vs the C336 residual | adopted (fix 3) |
| 14 | designer | fix 4's implementer edited two B7 frozen test-writer tests | reverted; amended by the test-writer (d5) — only a test-writer amends frozen tests |
| 15 | test-writer d5 F2 | `axis_plan("A5")` falls back to B7's single look when the report has no `variants` | declined: B3 binds `ids.json`'s A5 sizes and the report sha to the plan and refuses on mismatch, so a regenerated report without A5-2L is refused before any leg; residual recorded |
| 16 | test-writer d5 F3 | `joint.headline` / hours / direct check describe the single-look A5 reference | residual: the committed plan's figures are `joint.committed_plan`, verified by the test-writer's independent simulation |
| 17 | GLM F7 | scope extras (one-language column, grid ranges, per-option clean PASS, `pays` rule) | kept |

## Final plan (generated report; committed = TD + A5-2L, C338 / C339)

Clean PASS at no loss 38.37 % (nearest realisable A7 cell; 27.70 % at the extrapolated planning cell); A8 path false-clean at a
true 10 pp loss 0.43 %; A5 two looks (72 → 120, α 0.003808 / 0.021192, exact two-look size 2.164 %); GPU ≈ 66 h modelled / ≈ 72 h
whole stage expected (both arms). `m76_rule`: `axis_plan("A5")` two looks read from the report; `verdict_a5(..., alpha=)` (default
byte-identical); `A8_HOLD_PP = -0.20`, `a8_hold`.

## Tests

On the final candidate: test-writer 221, implementer 126, B7 + stats 343 — 690 pass.

## Accept

Operator Accept 2026-11-14 ("accepted", S23-P80; C340). Applied to `main`: the final candidate (`m76_sim.py`, `m76_rule.py`, the
implementer's `test_m76_b7_1_impl_*.py`, regenerated `benchmark/results/m76/b7-simulation/`, `report.json` `b1fbc9a5…`) and the
test-writer's tests (`test_m76_b7_1_fe_*.py`; its amendments of B7's `test_m76_b7_fe_fix_bound.py` / `test_m76_b7_fe_fix_report.py`).
On the operator's tree: 831 passed (B7 + B7.1 + stats + consumers).

```
[four-eyes 0.7.0] outcome: completed; mode: light
designer, implementer, fixes: Claude Code: Claude Opus 5.5 (designer); claude -p: Claude Opus, candidate fa19996d, fixes 499d3c77, f655ee9f, 78d2648a, 08e4d7b6
test-writer: claude -p: Claude Sonnet, 493be4f1; continued; tests frozen before the candidate was revealed (delivery 1)
panel: cold on candidate 1: cursor-agent gpt-5.6-sol-high, read-only snapshot, user instructions unconfirmed, returned; cursor-agent glm-5.2-high, same, returned; verify (fix 2, fresh sessions, briefed with the opinion): sol returned, glm returned
shared: implementer, test-writer and designer are Anthropic; not covered by them: errors Claude models make consistently (the panel is two other vendors)
go: C337 (2) (2026-11-14, "go with your rec above"); accept: C340 (2026-11-14, "accepted"); commit: see git log; push: none
```

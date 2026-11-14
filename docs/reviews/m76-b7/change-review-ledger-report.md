# M76 B7 — statistics for the M76 decision rule and its simulation — four-eyes light — ledger

Spec `docs/specs/m76-b7-statistics.md` v1 → v1.4 (v1.1 C331, v1.2 C335, v1.3 C336, v1.4 change-review dispositions, no rule change).
Baseline stack `e92418b5`. Copies `$STACK_WORKDIR/fe-m76b7/{impl,tw}/stack` (stack-only; `src/` empty by design).

## Cast

- Designer: Claude Opus 5.5 (this session).
- Implementer: Claude Opus via `claude -p` — candidate 1 (session `95a0ba49`), fix rounds 1–6 each a fresh session (`7bc9c32e`,
  `a6b4e481`, `3de196c5`, `71bfeea4`, `22dbd7e4`, `0f6abf8b`).
- Test-writer: Claude Sonnet via `claude -p`, one session continued (`dfe8825f`): delivery 1 (redone after the first attempt was
  blocked from running Python; frozen 2026-11-14T01:39:39Z, before the candidate was revealed 02:15:42Z), deliveries 2–6 (verdicts: d2 fix then merge; d3, d5 merge).
- Panel: GPT-5.6 Sol High (`gpt-5.6-sol-high`) and GLM 5.2 High (`glm-5.2-high`), `cursor-agent --mode ask`, read-only snapshot,
  user instructions unconfirmed; opinion on the fix-round-3 candidate, verify (fresh sessions, the runtime cannot continue) on fix 4.
- Shared: implementer and test-writer are both Anthropic models (as the designer); not covered by the Anthropic roles: errors Claude
  models make consistently — the two-vendor panel is the cover.

## Rulings during the run

C331 (S22-P25 / P26 as recommended; designer correction: the conditional Clopper–Pearson bound is unsafe, the exact unconditional test
replaces it — operator confirmed), C335 (A8 grid caps session SD at 0.25; A7 keeps concentration 4), C336 (A8 decider α* fixed at
0.001; corrects S23-P11's exposure statement).

## Findings

| # | raised by | finding | kind | disposition |
|---|---|---|---|---|
| 1 | candidate 1's own simulation | A5 / A8 final looks unsafe (false-PASS(10) upper 10.6 % / 5.2 %); disagreement flag fires 25 % / 14 % at no loss | original | → operator: C331 (spec v1.1) |
| 2 | fix 1's simulation | A8: no candidate α* safe on the pre-registered grid (SD 0.5 × D 0.30) | original | → operator: C335, then C336 |
| 3 | test-writer d2 F1, Sol P1, GLM F1 | the simulation certifies the exact bootstrap; stage 3 would call the 10,000-resample function (A1 look-1 counterexample) | original | adopted (fix 4): one function `m76_rule.exact_interval_values` for simulation and stage (`axis_verdict`) |
| 4 | test-writer d2 F2, Sol P2, GLM F2 | `loss_interval` / `verdict_of` fall back to the default 0.05 bound | introduced (candidate 1's wrapper) | adopted (fix 4): α required |
| 5 | Sol P3 | `recheck` ignores dispersion; mixes cells of different concentration | original | adopted (fix 4) |
| 6 | GLM F3 | A8 `final_safe` hides the SD 0.5 cells over 0.025 | introduced (fix 3) | adapted (fix 4, 5): "safe on the v1.2 grid" / "yes (v1.2 grid)" + `residual_cells` |
| 7 | GLM F4, GLM verify A4 | `recheck` has no session-SD dimension | original | declined: residual disclosed before and accepted in C336; the session × arm test on the decider data is the detector |
| 8 | GLM F5 | `unsafe_at_observed` broader than its name | original | adopted (fix 4): `unsafe_on_extended_grid` |
| 9 | GLM F6 | SD-0 interaction test accepted rate ≤ 0.05 with upper bound above | original | adopted (fix 4) |
| 10 | GLM F7 | byte-identity depends on numpy / interpreter | original | declined: numpy pinned in `benchmark/requirements-bench.lock`; versions recorded in the report |
| 11 | GLM F8, test-writer d2 F4 | A7 planning cell not realisable under the data model | original | adapted (fix 4): labelled, PASS(0) extrapolated, nearest realisable cell (87.31 %) beside it |
| 12 | GLM S1 / S2 | `discordance_upper95` null at non-default α; A5 annotation | scope request | kept (harmless; shown to the operator) |
| 13 | test-writer d2 F5 | `_check_exact` rejects numpy ints; stale "stdlib only" docstring | original | adopted (fix 4) |
| 14 | Sol verify P11, GLM verify A1 | spec / report text still name the resample rule; spec keeps `unsafe_at_observed` | repeated (documentation of #3 / #8) | adopted: spec v1.4 (designer) + M76 §8 pointer; report text (fix 5); `_AXES` statistic label (fix 6) |
| 15 | Sol verify P12 | a concentration above 4 keeps the κ = 4 calibration | introduced (fix 4) | declined: designer sweep (S23-P12) — A7 α* 0.001 at concentration 4 vs 0.0035 at 10–1000: 4 is the least favourable tested; residual in spec v1.4 |
| 16 | Sol verify P13, GLM verify A2, test-writer d3 F1, implementer P3 | `recheck` crashes at an observed pass rate of exactly 0 or 1 | repeated | adopted (fix 5): no recalibration; record flags `observed_unrealisable` / `operator_review` |
| 17 | Sol verify P14 | per-session intervals at α* instead of the descriptive 95 % | introduced (fix 4) | adopted (fix 5) |
| 18 | Sol verify P15, test-writer d3 F2, implementer P1 | size mismatches are `size_warnings`, not errors | scope request | B3 signals treat any size warning as blocking (→ operator); B7 unchanged |
| 19 | test-writer d3 F3, implementer P2 | `axis_plan("A1")` ignores the report's keep-look-1 decision | original | residual: harmless while the report keeps look 1 |
| 20 | test-writer d1 / d3 | five frozen tests faulty (repr inspection ×2, float endpoint, Wilson bound at 100 / 150 replications ×2) | test validity | judged invalid by the designer for the test-writer's own stated reasons; amended by the test-writer only (d3, d4) |
| 21 | test-writer d2 | `test_c147_chain_runner.py::test_stop_during_pilot_exit_3_archives_under_stopped` failed under load, passed alone | outside B7 | own item S23-P14 |

## Final plan (generated report)

A1 two looks (PASS(0) 99.955 %, false-PASS(10) upper 0.33 %); A5 one look, n = 72, exact unconditional test (PASS(0) 82.35 %, exact
size ≤ 2.5 % at every n 42–120); A7 one look over s1 + s2 + s3 at α* 0.001 (PASS(0) 64.10 % at the planning cell, extrapolated;
87.31 % at the nearest realisable cell); A8 decider one look at α* 0.001 (PASS(0) 50.77 %; safe on the v1.2 grid; 3 SD 0.5 cells up
to 2.82 % — C336 residual); session × arm test SD-0 firing ≤ 3.6 %.

## Accept

Operator Accept 2026-11-14 ("go with your rec above" on S23-P48; C337). Applied to `main`: the final candidate (`stats.py` additive,
`m76_rule.py`, `m76_sim.py`, implementer tests, generated `benchmark/results/m76/b7-simulation/`, `report.json` `dac5869f…`) and the
test-writer's tests (`test_m76_b7_fe_*.py`, amended per row 20). On the operator's tree: 484 passed (B7 implementer + test-writer
tests + `test_stats`, `test_compare*`, `test_agentbench_compare`). On commit the naming hook flagged two false positives; designer cosmetic edits, no behaviour change: the `stats.py` docstring citation spelled out ("Statistics in Medicine"), and a local variable `low` renamed `lowered` in `test_m76_b7_fe_sim.py` (66 affected tests re-run: pass). The stack gate runs after B3 lands (S23-P50).

```
[four-eyes 0.7.0] outcome: completed; mode: light
designer, implementer, fixes: Claude Code: Claude Opus 5.5 (designer); claude -p: Claude Opus, candidate 95a0ba49, fixes 7bc9c32e, a6b4e481, 3de196c5, 71bfeea4, 22dbd7e4, 0f6abf8b
test-writer: claude -p: Claude Sonnet, dfe8825f; continued; tests frozen 2026-11-14T01:39:39Z, candidate revealed 2026-11-14T02:15:42Z
panel: cold on candidate (fix 3): cursor-agent gpt-5.6-sol-high, read-only snapshot, user instructions unconfirmed, returned; cursor-agent glm-5.2-high, same, returned; verify (fix 4, fresh sessions, briefed with the opinion): sol returned, glm returned
shared: implementer, test-writer and designer are Anthropic; not covered by them: errors Claude models make consistently (the panel is two other vendors)
go: C325 (2026-11-11, "go"); accept: C337 (2026-11-14, "go with your rec above"); commit: see git log; push: none
```

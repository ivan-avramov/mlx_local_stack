# P359 audit: "wash" vocabulary replaces equivalence verdicts (C172)

Regrade only: every committed verdict file re-run over the committed rows with the P359 code (CPU only, `nice -n 19`, no server). No score, point estimate, CI or MDE changed (checked field by field in `rerun_*.log`; the only diffs are verdict labels plus the new `directional` / `verdict_note` / `wash_label` fields and the P346/P348 diagnostics). Scripts: `scripts/rerun_cp.py`, `rerun_jg.py`, `rerun_ab.py` (P348 scripts with the output root moved; run from `benchmark/` with `P359_OUT=<this dir>`). Originals in `benchmark/results/` are untouched; regenerated outputs are in `compare_predictor/`, `judge_gate/`, `agentbench_compare/`.

Vocabulary: `paired_delta` verdict is `a_better` / `b_better` (95 % CI excludes 0) or `wash` (CI includes 0) plus `directional` (`a`/`b`/`tie`) and the axis `mde`; `stats.verdict_label` prints `wash (MDE x pp; directional: <pick> (not a shown difference))` (`directional: tie` on an exact tie). `compare_predictor` verdicts are `PASS` / `FAIL` / `loss_not_ruled_out` (C173 guard); judge ranking verdicts are `m1_better` / `m2_better` / `wash`. Retired strings: `equivalent`, `inconclusive` (as a paired verdict), `equivalent_95ci_within_5pp`, `no_discordance_equivalence_not_established`, "equivalence NOT established".

## Lever guard (C173 supersedes the C172 MDE guard)

A wash ships a lossy lever only when the observed interval rules out a loss > 10 pp: CI lower bound >= -10 pp, or, for a degenerate zero-discordance cell, the exact one-sided 95 % discordance bound (`discordance_upper95`) <= 10 pp. Otherwise `loss_not_ruled_out` ("loss not ruled out above X pp"). A point estimate beyond -5 pp and a shown loss beyond the margin still FAIL. (The first P359 version used axis MDE <= 10 pp, which needs n >= 157 and downgraded all 12 cells; that guard is gone.)

Result: **all 12 stored `compare_predictor` cells are PASS (ship-eligible)**; the printed loss bounds are 0 pp (three non-degenerate cells whose CI lower bound is 0: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` M57 HumanEvalPlus +2 pp and Math500 M40, `Qwen3.8-27B-mlx-uniform-4bit` HumanEvalPlus), 3 pp (`Qwen3.8-27B-mlx-uniform-4bit` Math500, n=100 zero discordance), 6 pp (the eight M57 n=50 zero-discordance cells and `Qwen3.8-27B-mlx-uniform-4bit` MBPPPlus, CI [-6, +3]). No lever changes ship status relative to the original stored verdicts except that the earlier PASS/INCONCLUSIVE labels are now all PASS with wash numbers; none is blocked. See `compare_predictor/*` (`verdict_note` per file).

## Label changes in code-produced outputs

| output | cells | old -> new |
|---|---|---|
| `compare_predictor/*` (12 files) | 12 top-level verdicts; 24 per-metric paired verdicts (acc, acc_strict) | PASS x8 / INCONCLUSIVE x4 -> PASS x12 (C173 guard; bounds 0-6 pp); `equivalent`/`inconclusive` -> `wash` (+`directional`) |
| `judge_gate/judge_c_v1/ranking.json` | 10 pairs | unchanged (9 `m2_better`, 1 `m1_better`; none was a wash); new `directional` / `wash_label: null` fields |
| `judge_gate/judge_m40/*`, `judge_m60/*` ranking (3 files) | 3 pairs | `inconclusive` -> `wash`, with `wash_label` (MDE 20 pp) |
| `judge_gate/*/gate.json` (reliability gates) | 5 files | unchanged (PASS 6/6, identical metrics) |
| `agentbench_compare/chain{1,3,4}` | 30 pairs | `inconclusive` -> `wash` for every non-shown pair; `a_better`/`b_better` unchanged; no degenerate pair |

## Label changes in committed reports (numbers byte-identical, checked by diffing each row with the verdict cell removed)

| report | verdict cells | header cells | old -> new |
|---|---|---|---|
| `benchmark/results/p223_tg1/P223_REPORT.md` | 16 | 6 | `inconclusive` x9, `no discordance — equivalence NOT established` x7 -> `wash (MDE 27 pp; directional: ...)` |
| `benchmark/results/m63_mtp/M63_REPORT.md` | 16 | 8 | same |
| `benchmark/results/c144_base/C144BASE_REPORT.md` | 16 | 6 | same |
| `benchmark/results/m61_rr/RR_REPORT.md` | 12 | 4 | `equivalent` x1, `inconclusive` x11 -> wash (relabelled by hand: `rr_report.py` inputs under `$STACK_WORKDIR/m61` are not on this box; the script was updated identically) |

Header `verdict (TOST ±5 pp)` -> `verdict (CI excludes 0, else wash)`.

## Docs changed (wording only; no YAML value changed, `main_models.yaml` parses to the identical object)

- `README.md` (11 edits): P223/M63 ON-vs-OFF lines for both picks, the TOST `a_better` mention, the second-pick M40 row, the M60 Math500 INCONCLUSIVE clause, the M57 "not proven equivalent" clause, two "equivalence" disclaimers in the Phase 2 paragraph. CERTIFIED/PROVISIONAL tags untouched.
- `main_models.yaml` comments (13 lines): C-order "EQUIVALENT at equal length" (two places), M27 `Ornith-1.0-35B-mlx-uniform-4bit` and M6b/M6d TOST EQUIVALENT lines, M40 `Qwen3.8-27B-mlx-uniform-4bit` certification line, M57 line, M32/S2b/M21b `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` lines. CERTIFIED annotation format kept.
- `docs/campaign-results.md` (about 53 edits): P223/M63/c144-base prose, M40 table rows and heading, M57 paragraphs, Ornith/C63 Math500 fallback cells, M24/M32/M32b/S2b/S2c/M27/M6d historical EQUIVALENT cells (rewritten as wash with MDE and directional pick; the historical rules' "EQUIVALENT" condition is stated as the then-rule's CI condition), IFEval n=148, the grader-read note.
- Left as is (they only deny equivalence or use the word in another sense): campaign-results lines on five-item pilots "cannot establish equivalence", "GPU equivalence", "upstream-equivalent", "population-equivalence claim".
- Historical machine records not relabelled (already marked non-operative, P348): `raw_helper_verdict: "equivalent"` fields in `m42_*`, `m43_*` JSON; the stored `paired_*.json` originals.

## Judgement calls

- Directional picks in historical prose were derived from the sign of the quoted delta; where a doc gave no sign (the adjusted +0.25 C-order panel read) the text says "directional point estimate only".
- `loss not ruled out above X pp` uses X = -CI lower bound, or the exact discordance bound for a degenerate cell (C173).
- Remaining mentions of "inconclusive" in campaign-results that are not paired-delta verdicts (e.g. "inconclusive n=63 pilot" narratives, other gates) were not rewritten.

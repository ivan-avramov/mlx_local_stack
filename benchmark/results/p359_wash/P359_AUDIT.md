# P359 audit: "wash" vocabulary replaces equivalence verdicts (C172)

Regrade only: every committed verdict file re-run over the committed rows with the P359 code (CPU only, `nice -n 19`, no server). No score, point estimate, CI or MDE changed (checked field by field in `rerun_*.log`; the only diffs are verdict labels plus the new `directional` / `verdict_note` / `wash_label` fields and the P346/P348 diagnostics). Scripts: `scripts/rerun_cp.py`, `rerun_jg.py`, `rerun_ab.py` (P348 scripts with the output root moved; run from `benchmark/` with `P359_OUT=<this dir>`). Originals in `benchmark/results/` are untouched; regenerated outputs are in `compare_predictor/`, `judge_gate/`, `agentbench_compare/`.

Vocabulary: `paired_delta` verdict is `a_better` / `b_better` (95 % CI excludes 0) or `wash` (CI includes 0) plus `directional` (`a`/`b`/`tie`) and the axis `mde`; `stats.verdict_label` prints `wash (MDE x pp; directional: <pick> (not a shown difference))` (`directional: tie` on an exact tie). `compare_predictor` verdicts are `PASS` / `FAIL` / `loss_not_ruled_out`; judge ranking verdicts are `m1_better` / `m2_better` / `wash`. Retired strings: `equivalent`, `inconclusive` (as a paired verdict), `equivalent_95ci_within_5pp`, `no_discordance_equivalence_not_established`, "equivalence NOT established".

## FLAG: lever guard (needs an operator decision)

Guard as ruled: a wash passes a lossy lever only at axis MDE <= 10 pp. `stats.mde` is the McNemar approximation with p_d = 0.20, so MDE <= 10 pp needs n >= 157 paired items (n=164 gives 9.8 pp; **n=100 gives 12.5 pp; n=50 gives 17.7 pp**). The P359 proposal text said "in practice single-turn axes at n >~ 100"; that is not what the formula gives. Consequence: **every one of the 12 stored `compare_predictor` cells becomes `loss_not_ruled_out`** (none is FAIL, none is a shown loss, none has an OFF advantage beyond +-5 pp):

| file (under `benchmark/results/`) | n | strict delta (B-A) [CI] | MDE pp | directional | stored | new |
|---|---|---|---|---|---|---|
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/humanevalplus.m57b-q1.vs.m57a-q1.json` | 50 | +0.020 [+0.000, +0.060] | 17.7 | tune_b | INCONCLUSIVE | loss_not_ruled_out |
| same dir `humanevalplus.m57b-q2.vs.m57a-q2.json` | 50 | +0.000 [0, 0] | 17.7 | tie | PASS | loss_not_ruled_out |
| same dir `humanevalplus.m57e-q1.vs.m57b-q1.json` | 50 | +0.000 [0, 0] | 17.7 | tie | PASS | loss_not_ruled_out |
| same dir `humanevalplus.m57e-q2.vs.m57b-q2.json` | 50 | +0.000 [0, 0] | 17.7 | tie | PASS | loss_not_ruled_out |
| same dir `mbppplus.m57b-q1.vs.m57a-q1.json` | 50 | +0.000 [0, 0] | 17.7 | tie | PASS | loss_not_ruled_out |
| same dir `mbppplus.m57b-q2.vs.m57a-q2.json` | 50 | +0.000 [0, 0] | 17.7 | tie | PASS | loss_not_ruled_out |
| same dir `mbppplus.m57e-q1.vs.m57b-q1.json` | 50 | +0.000 [0, 0] | 17.7 | tie | PASS | loss_not_ruled_out |
| same dir `mbppplus.m57e-q2.vs.m57b-q2.json` | 50 | +0.000 [0, 0] | 17.7 | tie | PASS | loss_not_ruled_out |
| same dir `math500.m40on.vs.m37med.json` | 100 | +0.020 [+0.000, +0.050] | 12.5 | tune_b | INCONCLUSIVE | loss_not_ruled_out |
| `Qwen3.8-27B-mlx-uniform-4bit/humanevalplus.m40on.vs.m40off.json` | 100 | +0.010 [+0.000, +0.030] | 12.5 | tune_b (ON) | PASS | loss_not_ruled_out |
| `Qwen3.8-27B-mlx-uniform-4bit/math500.m40on.vs.m37med.json` | 100 | +0.000 [0, 0] | 12.5 | tie | PASS | loss_not_ruled_out |
| `Qwen3.8-27B-mlx-uniform-4bit/mbppplus.m40on.vs.m40off.json` | 100 | -0.010 [-0.060, +0.030] | 12.5 | tune_a (OFF) | INCONCLUSIVE | loss_not_ruled_out |

(The stored `m57*` PASS labels were already INCONCLUSIVE after P348; the M40 `humanevalplus` PASS is a new downgrade, since its CI [0, +3] pp is non-degenerate and was a genuine PASS under P346.)

Levers affected and what the guard means for each (the certifications are C71/C115 "no FAIL" rules, so nothing flips mechanically and no registry value changed):

- `Qwen3.8-27B-mlx-uniform-4bit` MTP ON (M40): HumanEvalPlus, Math500 and MBPPPlus all `loss_not_ruled_out` at n=100 (MDE 12.5 pp). Operator call needed: keep "SHIPS ON / CERTIFIED M40" on the C71 no-FAIL rule, or require more items (n >= 157 per axis).
- `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` M57 `fused_v1` and lazy embeddings: eight zero-discordance n=50 cells plus one +2 pp cell, all `loss_not_ruled_out` (MDE 17.7 pp). The M57 adoption also rests on byte-identical outputs on 200/200 prompts, which the guard does not see.
- `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` M40/M60 Math500 ON-vs-OFF cell: `loss_not_ruled_out`.
- Pre-`compare_predictor` ON/OFF certifications quoted in `main_models.yaml` (M27 `Ornith-1.0-35B-mlx-uniform-4bit` n=164, MDE 9.8 pp; M6d `Qwen3.8-27B-mlx-uniform-4bit` n=164, MDE 9.8 pp) would PASS the guard (n=164 is just under 10 pp). The M6b n=63 cell (`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, MDE 15.8 pp) would not; those were not stored as `compare_predictor` files and were not re-run.

Possible refinement (not implemented; the ruling says MDE): ship on a wash when the CI lower bound is >= -10 pp as well. It would pass the nondegenerate cells above (e.g. `humanevalplus` [0, +3]) but would wrongly pass the zero-discordance cells, whose collapsed CI says nothing (P358). The MDE rule is the safer proxy; the cost is the n >= 157 requirement.

## Label changes in code-produced outputs

| output | cells | old -> new |
|---|---|---|
| `compare_predictor/*` (12 files) | 12 top-level verdicts; 24 per-metric paired verdicts (acc, acc_strict) | PASS x8 / INCONCLUSIVE x4 -> `loss_not_ruled_out` x12; `equivalent`/`inconclusive` -> `wash` (+`directional`) |
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
- `loss not ruled out above X pp` uses X = max(-CI lower bound, axis MDE) so a CI whose lower bound is 0 does not read as "above 0 pp".
- Remaining mentions of "inconclusive" in campaign-results that are not paired-delta verdicts (e.g. "inconclusive n=63 pilot" narratives, other gates) were not rewritten.

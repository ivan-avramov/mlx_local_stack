# P348 audit: stored verdicts re-run with the P346 logic (C167)

Scope: every committed verdict file produced by `bench.compare_predictor`, `bench.judge_gate` and `bench.agentbench_compare`, re-run over the committed rows/inputs with current code (CPU only, no server). Originals are untouched; regenerated outputs are in this directory. Scripts: `scripts/rerun_cp.py`, `scripts/rerun_jg.py`, `scripts/rerun_ab.py` (run from `benchmark/`; scratch output under `$TMPDIR/p348`).

Result: 12 compare_predictor + 4 judge ranking + 3 agentbench_compare files audited (plus 4 of 5 judge `gate.json` reliability files re-checked); **8 verdicts change, all in `compare_predictor`, all PASS to INCONCLUSIVE**; no `judge_gate` or `agentbench_compare` verdict changes. Every score, point estimate and CI is identical old vs new (checked field by field); the only diffs are the verdict label and the new `degenerate` / `discordance_upper95` / `must_differ` / `differ_*` fields. No shipping decision changes: none of the 8 cells has an OFF-side (or B-side) advantage; the rule "ship OFF only on an OFF advantage beyond +-5 pp" is untouched.

## 1. compare_predictor (12 files; `key=acc_strict`, margin 0.05)

`discordance_upper95` = exact one-sided 95% upper bound on the discordance rate when 0 of n pairs are discordant.

| file (under `benchmark/results/`) | n | strict delta [CI] | old | new | discordance_upper95 | status |
|---|---|---|---|---|---|---|
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/humanevalplus.m57b-q1.vs.m57a-q1.json` | 50 | +0.020 [+0.000, +0.060] | INCONCLUSIVE | INCONCLUSIVE |  | unchanged |
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/humanevalplus.m57b-q2.vs.m57a-q2.json` | 50 | +0.000 [+0.000, +0.000] | PASS | INCONCLUSIVE | 5.8 pp | **CHANGED** |
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/humanevalplus.m57e-q1.vs.m57b-q1.json` | 50 | +0.000 [+0.000, +0.000] | PASS | INCONCLUSIVE | 5.8 pp | **CHANGED** |
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/humanevalplus.m57e-q2.vs.m57b-q2.json` | 50 | +0.000 [+0.000, +0.000] | PASS | INCONCLUSIVE | 5.8 pp | **CHANGED** |
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/math500.m40on.vs.m37med.json` | 100 | +0.020 [+0.000, +0.050] | INCONCLUSIVE | INCONCLUSIVE |  | unchanged |
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/mbppplus.m57b-q1.vs.m57a-q1.json` | 50 | +0.000 [+0.000, +0.000] | PASS | INCONCLUSIVE | 5.8 pp | **CHANGED** |
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/mbppplus.m57b-q2.vs.m57a-q2.json` | 50 | +0.000 [+0.000, +0.000] | PASS | INCONCLUSIVE | 5.8 pp | **CHANGED** |
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/mbppplus.m57e-q1.vs.m57b-q1.json` | 50 | +0.000 [+0.000, +0.000] | PASS | INCONCLUSIVE | 5.8 pp | **CHANGED** |
| `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/mbppplus.m57e-q2.vs.m57b-q2.json` | 50 | +0.000 [+0.000, +0.000] | PASS | INCONCLUSIVE | 5.8 pp | **CHANGED** |
| `Qwen3.8-27B-mlx-uniform-4bit/humanevalplus.m40on.vs.m40off.json` | 100 | +0.010 [+0.000, +0.030] | PASS | PASS |  | unchanged |
| `Qwen3.8-27B-mlx-uniform-4bit/math500.m40on.vs.m37med.json` | 100 | +0.000 [+0.000, +0.000] | PASS | INCONCLUSIVE | 3.0 pp | **CHANGED** |
| `Qwen3.8-27B-mlx-uniform-4bit/mbppplus.m40on.vs.m40off.json` | 100 | -0.010 [-0.060, +0.030] | INCONCLUSIVE | INCONCLUSIVE |  | unchanged |

The four `m57b-vs-m57a` humanevalplus/mbppplus q1/q2 cells and the four `m57e-vs-m57b` cells are the M57 qualification axes (`fused_v1` vs `auto`; lazy embeddings vs `fused_v1`); the M40 cell is `Qwen3.8-27B-mlx-uniform-4bit` Math500 ON vs OFF. Unchanged non-degenerate cells: M40 HumanEvalPlus (PASS, CI [0, +3] pp), the two INCONCLUSIVE Math500/MBPPPlus cells, and `humanevalplus.m57b-q1.vs.m57a-q1` (+2 pp [0, +6], INCONCLUSIVE).

## 2. judge_gate (4 ranking files, 13 pair verdicts; 5 gate files)

Re-run of `compute_ranking` (seed 0) and `compute_gate`: ranking verdicts and numbers identical. No stored verdict was `equivalent_95ci_within_5pp`: `judge_c_v1/ranking.json` holds 10 pairs (9 `m2_better`, 1 `m1_better`); the three `judge_m40` / `judge_m60` rankings are one `inconclusive` pair each. The `gate.json` files are reliability gates (kappa, alpha, order flips), not equivalence verdicts; all re-compute PASS with identical metrics (only the `judges` list order differs). `gate.anchors3.json` was not separately re-run (same code path, anchors subset of `judge_c_v1`).

## 3. agentbench_compare (3 files: chain1, chain3, chain4; 10 pairs each)

Rebuilt from `results/<model>/agentbench_os.v1.chain{1,3,4}.jsonl` (+ manifests for chain 4, as in the stored command). Identical except for the new `delta.degenerate` / `delta.discordance_upper95` fields; no pair is degenerate (every pair has discordant items), no `equivalent` verdict was stored.

## 4. Not re-runnable / out of the three tools

- Nothing in the three tools' stored outputs was missing inputs. The `.md` companions of the agentbench reports were not regenerated (JSON is the audit object).
- Stored `stats.paired_delta` outputs from ad hoc analysis scripts (not the three tools; the scripts are not committed, only their JSON): three degenerate `equivalent` cells, identified from the stored CI [0, 0] with n=100 (discordance_upper95 = 3.0 pp): `paired_c63_math500.json` pairs[0] `acc_delta_fallback`; `paired_ornith_math500.json` pairs[2] `acc_delta_fallback` and pairs[3] `acc_compare`. These are not re-run (no tool); the docs wording was relabelled. All other stored `equivalent` cells in `paired_*.json` have non-degenerate intervals (checked).
- P223 / M63 / c144-base report helpers: already relabelled by P346 (22 label lines); the campaign-results prose still carried "(equivalent)" in two head-to-head sentences, relabelled here.
- The M24/M27/M21b/M32 equivalences quoted in the docs have non-degenerate CIs (positive width, discordant items on both sides); the IFEval n=148 `equivalent` (89.9% vs 89.9%) predates the stored-file layout and its interval was not checked; not re-run.

## 5. Docs relabelled (wording only; no YAML value changed)

- `docs/campaign-results.md`: P223 and M63 head-to-head "(equivalent)" cells (2 places); M40 pick B Math500 table row PASS to INCONCLUSIVE (no discordance, discordance <= 3.0 pp) and the section heading (PASS x5 to x4); M57 lazy-embeddings paragraph, M57 stage-2 delta paragraph and Q1 rule line (no-loss threshold, not equivalence; discordance <= 5.8 pp per n=50 cell); the three `CI[0,0]` "equivalent" fallback cells (Ornith Math500 x2, C63 Math500 x1).
- `main_models.yaml` comments: `Qwen3.8-27B-mlx-uniform-4bit` CERTIFIED M40 line (Math500 0 discordant); `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` CERTIFIED M57 line (humanevalplus/mbppplus +2 / 0). CERTIFIED annotation format kept.
- `README.md`: second-pick row (M40 Math500 axis). The M57 README row already read "within tolerance, not proven equivalent".

## 6. Operator judgement

None required for shipping. One wording choice to confirm: the M40 pick B certification stays "CERTIFIED" because the pre-registered rule (C71: any FAIL flips OFF, else ships ON) is a no-FAIL rule; only the "equivalence" reading of the zero-discordance Math500 axis was withdrawn.

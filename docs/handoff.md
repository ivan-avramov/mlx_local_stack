# Handoff — rewritten 2026-08-21 ~15:45 (pre-compaction checkpoint; gate-3 M16 leg live)

Single box (M5 Max 64 GB). Stack pushed through `df30685`; ~16 local-only commits after —
push awaits operator approval. Intentional dirt: `main_models.yaml` (six candidate entries,
$HOME-local hf_paths) + probe artifacts in `$STACK_WORKDIR/status/m19_scan/`, `m20_scan/`.

## Live right now (RESTART-SENSITIVE)

- **Gate-3 re-screen, M16 leg**: `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` hep n=50 at
  t0.5, was 24/50 zero DNFs (terse-or-very-long-CONVERGING profile, ~35-min tail items, no
  runaways); mbpp n=50 follows in the same driver. ⚠️ The driver is a claude-code-tracked
  background task (`bnit05env`) — **a claude-code restart may kill it. That is SAFE**: resume
  loses at most the in-flight item. Relaunch (nohup-detached, resumes on done rows):
  `cd $STACK_REPO/benchmark && nohup $STACK_REPO/.venv-bench/bin/python run.py generate
  --models Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit --benches humanevalplus,mbppplus
  --limit humanevalplus=50,mbppplus=50 --temp 0.5 --tune t0.5 --probe-timeout 3600
  --order model > $STACK_WORKDIR/status/gate3_m16.log 2>&1 </dev/null &`
  Verify with pgrep + row-count advance. Two `bench_watch` watchers (nohup'd, survive
  restart): `$STACK_WORKDIR/status/gate3_{hep,mbpp}.watch`.
- **M15 gate-3 COMPLETE**: `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` at t0.5 — hep 50/50
  ZERO DNFs, mbpp 50/50 one DNF (`Mbpp/440`) = **1% total, was 10% at t0.6**. UNGRADED —
  grade with the M16 arms when its leg finishes.

## On M16-leg completion (the standing closeout)

1. Grade all four t0.5 arms serially in docker (`run.py grade --tune t0.5`, per model×bench).
2. Compares: each vs `Qwen3.8-27B-OptiQ-4.5bpw-mixed@t0.6` `--intersect`, PLUS the admissible
   incumbent compare `Qwen3.6-27B-Opus-Distill-OptiQ-4bit@t0.3` (same cap 262144).
3. D13 (queued, zero GPU): corpus-wide DNF/convergence sweep by quant recipe × bits from
   existing rows — cross-check of the precision-drives-runaways hypothesis before M21.
4. Regenerate scoresheet, ledger fold (t0.5 = SHIPPED-CONFIG characterization, the
   recommendation-bearing rows per operator ruling), rewrite this file, commit each (verify
   with `git log` — rtk "ok" lies).
5. Propose `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` for the M3/M4 opencode roster
   (operator has seen the suggestion, not yet ruled).

## The knee story (M19/M20 CLOSED, both knees t0.5)

- M19 `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`: scan knee t0.5; DNF-first 7/10 converted;
  rung acc 1.000 (holds); gate-3 CONFIRMED IT — 1% DNF at full budget, ~4× faster wall.
- M20 `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`: all scan temps converge; DNF-first
  9/14; rung acc 0.867 (holds); gate-3 leg in flight.
- ⚠️ **Capped-probe FALSE NEGATIVES**: `HumanEval/32` and `Mbpp/306` failed the 8192-cap probe
  yet CONVERGED at full budget — the cap is too tight for honest long traces. Scan-recipe
  caveat: a capped non-conversion is evidence, not proof; only the full-budget arm settles it.

## Standings after gate-3 (single-shot, at each model's shipped tune)

Incumbent `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`@t0.3: hep 93.8/90, mbpp 81.6/80, ~3% DNF —
B pick STANDS (head-to-head vs `Qwen3.8-27B-OptiQ-4.5bpw-mixed` INCONCLUSIVE both benches).
`Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`@t0.5: hep acc ≈95 expected ≈strict (1 DNF/100),
grades pending — likely the corpus's strongest hep row. The online-vs-us tension RESOLVED as
config: temp knee (t0.5 not the base's t0.6) + quant recipe (4-bit uniform) + acc_strict
charging DNFs; on DNF-excluded acc the family was never behind.

## Queue after the closeout

M3/M4 (opencode — the REAL differentiator; no 3.8-family model has agentic evidence) →
M5 remnant → M18 (BFCL) → M7 → M21 conversions in a quiet window (int8 control +
mixed-precision treatment on the `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` base, arms
AFTER M3/M4; M22 contingent) → D10 submodule bump → F1+F2 → M11/M12 → D11 cards → D6 → M14
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` MTP probe.

## Traps refreshed this session

`--ids` are COLON-separated (`bench=id1:id2`; comma = the `--limit` separator — a comma list
silently probes ONE item). zsh does not word-split `set -- $var` (six grades failed rc=2).
Relative venv paths die when the session cwd moves — absolute paths in every background task.
Probe artifacts move OUT of `benchmark/results/` (else they resume-collide with real arms).
Verify every commit with `git log`; verify every detached launch by process AND output file.

**Order of resumption: this file → `docs/PLAN.md` → `docs/work-queue.json` →
`$STACK_WORKDIR/status/` (live runs).**

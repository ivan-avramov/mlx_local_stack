# Handoff — 2026-09-02 17:00 (M21 CLOSED negative; M21b k=3 confirmation IN FLIGHT; O30 guard lifted; C41/C45/P8 landed)

Single box (M5 Max 64 GB). **ONE detached job is LIVE:** the M21b k=3 chain (`$STACK_WORKDIR/m21/k3_chain.py`,
pid `m21/k3.pid`, log `m21/k3.log`, driver logs `m21/k3_*.log`, launched 16:51): adds samples 1–2 to the
existing k=1 rows of `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5 (then of
`Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` @t0.6-r2), same 50 hep items, seeds paired per (item, sample),
bound 7800 s, predictor OFF, then grades both at k=3 and runs `compare REF@t0.6-r2,OPT@t0.5` (+ `--intersect`).
ETA ≈ 2.5 h per arm + meander tail (`HumanEval/32`/`99` can run 80 min each) → done ≈ 22:00–01:00. Router
is UP on the M21 overlay `$STACK_WORKDIR/m21/bench_overlay_m21.yaml` (int8 entry removed; overlay sha
`90b3606c…`). Monitor: `tail -F m21/k3.log` (pid liveness first). **`src/mlx-vlm` WORKTREE IS PINNED at
`57177a21`** (stack HEAD points at `7330d3a6` = C45, splitter-only) so k=3 rows pair with the ladder; the venv
imports `src/mlx-vlm` editable. **RESTORE after the run: `git -C src/mlx-vlm checkout 7330d3a6`** (then
`git status` shows the submodule clean).

Fork main = `7330d3a6` (pushed). Stack pushed through `94ac286` (17:05, operator-approved) plus the 17:15 batch
below — push needs in-turn approval every time. Working tree: the SIX intentional `main_models.yaml` overrides
(NEVER commit), the pinned submodule worktree (`M src/mlx-vlm`, NEVER commit) + the live k=3 rows file.

## Where M21/M21b stand (campaign-results 2026-09-02, PLAN M21 + M21b)
- **M21 CLOSED, negative**: three precisions of the same checkpoint converge on all 50 items; strict 88.0
  (uniform-4bit re-measured `t0.6-r2`) / 88.0 (mixed) / 86.0 (int8); paired deltas INCONCLUSIVE. The <!-- allow-shorthand -->
  2026-08-20 "10 % DNF" was a pre-C28 client-timeout cascade (positions 16-17, 22-24-25), not runaways.
- **M21b ladder DONE** (`5dc5b1f`, `9c746f7`): mixed @t0.4/0.5/0.6/0.7 → strict 45/44/44/44, all INCONCLUSIVE.
  Tokens over 50 items 161K/90K/92K/180K, dominated by two BIMODAL items (`HumanEval/32`, `99`: 5K one draw,
  82K the next). t0.5 has the best ordinary-item cost (median 408, p90 1628). Operator's decision axis is
  TOKENS PER TASK at equal quality; the pre-registered frame is P28 (PLAN M21b row) with a joint review
  before any registry change — **do not touch the registry on the k=3 result alone**.
- When `=== M21b K3 DONE ===` appears: read `m21/grade_k3_*.log`, `m21/compare_k3*.log`; compute the
  paired tokens-per-task ratio (mean over 3 samples per item, cluster bootstrap over items) and mean
  strict per arm; present data + rule verdict + recommendation to the operator; then mbpp (step 4:
  mixed at the chosen rung n=50 + the 4-bit's mbpp re-measured `t0.6-r2`, its existing row is pre-C28). <!-- allow-shorthand -->

## Landed this session
- C41 (fork `57177a21`) and C45 (fork `7330d3a6`, submodule `1f4f80d`): qwen3_5 MTP splitter fixes, verified.
- P8 (`9823a31` + backfill `c14aab6`, `5dc5b1f`): local-path manifests carry their quantization block again.
- O30 CLOSED (`7df1be3`, `d84ecc5`): `--samples k` accepted; the 2-seed probe passed on the live router.
- C47 filed: `compare`'s code-sha guard keys on the whole submodule commit — needs a ruling.

## THE BOX QUEUE (after k=3)
1. M21b review + mbpp (above). 2. **C46**: re-measure pre-C28 timeout rows behind live rulings, in order
   `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` hep+mbpp @t0.55/@t0.6 (O37), then
   `Qwen3.8-27B-mlx-uniform-4bit` vs `Qwen3.8-27B-OptiQ-4.5bpw-mixed` hep+mbpp @t0.6 (M25). Full n=50 re-runs
   (partial resume would mix code versions in one file). 3. M17 / D11 / M18.

## Resolved 17:15 (operator took the session recommendations)
- The pre-session untracked rows are COMMITTED: M27/M6d certification rows `5b8f4de`, M23 rows `3ea3d9c`
  (DO-NOT-CITE caveat in the commit body). The root `transcript.md` was a third-party video transcript, moved
  to `$STACK_WORKDIR/notes/`. Tree has zero untracked files.
- **C46 FILED** (open-questions) as the pre-C28 timeout re-measurement queue item; box slot after M21b.
- **C47**: session recommendation recorded in the row (adopt the serving-path tree hash as a v4 fingerprint
  field beside the commit sha; historical rows stay pairable by derivation). Build after the k=3 review, not
  before. Still needs the operator's ruling on the row itself.
- The k=3 analysis script is `$STACK_WORKDIR/m21/k3_analysis.py` (P28 rule, paired tokens-per-task ratio
  with a two-stage item bootstrap; warns on a stale evalplus result). `bench_watch` was launched with
  `--total 50`, so its ETA line is meaningless at k=3 (rows > items) — progress is read from the rows file.

## Standing rules that bit this session
- A fallback LIST of candidate artifact dirs is a wrong-artifact generator (M21 runner served `static_mixed`
  for 2 min): name the ONE admissible artifact; resolve safetensors-index names as paths (sidecars in subdirs).
- `compare` refuses across fork shas; a reference older than the last fork bump must be re-measured before any
  paired claim; a fork bump landing MID-A/B splits the arms — pin the worktree.
- `ps -Eww` truncates the env block behind a long command line — verify `MLX_SERVE_CONFIG` via the
  manifest's `registry.sha256`, not `ps`. A RESUMED run keeps its original manifest (sha of that day's overlay).
- The converter's stdout is block-buffered; read `sensitivity_checkpoint.json` for progress. Its bpw line is
  per phase and is not the manifest's `effective_bits`.
- k=1 draws on meander-prone items are bimodal (5K vs 82K tokens on the same seed across sessions);
  never read a single draw's token count as a recipe property.

## Artifacts
M21/M21b `$STACK_WORKDIR/m21/` (runners, logs, temp overlay, `wrong_artifact_2026-09-01/`); the mixed artifact
`$STACK_WORKDIR/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/optiq_mixed` (18 GB, KEEP until M21b
closes; upload to `caslca/` only if it becomes a pick); int8 + byproducts DELETED 2026-09-02. HF cache holds
the `TeichAI/Qwen3.8-27B-Fable-Distill` bf16 source <!-- allow-shorthand --> (54 GB, deletable once no further conversion is planned).

**Order of resumption: this file → `$STACK_WORKDIR/m21/k3.log` (alive? done?) → `docs/PLAN.md` (M21b) → `docs/open-questions.md` (C46, C47).**

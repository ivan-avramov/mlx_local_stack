# Handoff — 2026-09-03 18:10 (M21b CLOSED — recipe CARRIED + CERTIFIED; C47 shipped; docs reorganized; box IDLE)

Single box (M5 Max 64 GB). **NO detached job is live.** Router is still UP on the M21 overlay
(`$STACK_WORKDIR/m21/bench_overlay_m21.yaml`, worker idle, last served `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`);
restart it on whatever overlay the next job needs. `src/mlx-vlm` worktree RESTORED to the stack pointer `7330d3a6`
(submodule clean). OrbStack must be running for evalplus grading (it went down once today with an operator workload;
`open -a OrbStack` brings it back in ~6 s).

Stack pushed through `b723bde`. **UNPUSHED: `6ae5772` (docs reorg), `19e6fbb` (C47), `3d08faa` (handoff), `e7810e8`
(mbpp k=3 rows), `c95123f` (M21b certification + registry), + this handoff commit** — push needs in-turn approval.
Working tree: SEVEN intentional `main_models.yaml` local-path overrides (the six from before + the new
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` entry pointing at `$STACK_WORKDIR/optiq_out/.../optiq_mixed`) — NEVER commit;
when the registry needs a committed edit, build the index blob from `git show HEAD:main_models.yaml` (done twice today).

## M21b CLOSED 2026-09-03 (campaign-results entry; PLAN row DONE)
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5 vs `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` @t0.6-r2, k=3 on
hep (`c4216b9`) and mbpp (`e7810e8`): strict EQUIVALENT pooled n=100 (+0.7pp CI [−2.7, +4.3]); tokens-per-task ratio
0.66 / 0.64 per bench, pooled **0.650 CI [0.455, 0.880]**; P28 met on both benches (mbpp on all three conditions).
Operator ruled CARRY: uploaded `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (public, 15 files, sha-verified,
card with the paired results), registry entry @t0.5 `# CERTIFIED M21b 2026-09-03`, candidate role, draft-OFF (triple
rule applies only on promotion; the artifact carries an MTP head sidecar, untested). Bench carriers regenerated
(`configgen`), check clean. Mechanism: the recipe trims the verbose/bimodal tail, not the chronic failures.

## Landed 2026-09-02 evening → 2026-09-03
- **C47 SHIPPED (`19e6fbb`)**: fingerprint v5 = serving-path tree hash beside the commit sha; `compare` refuses only on a
  serving-path change; older manifests derive it. Spec `docs/specs/c47-serving-path-fingerprint.md`. Live: `57177a21`
  ≡ `7330d3a6` ≡ `f5fff9b5`; `ab5708a` differs.
- **Docs reorganized (`6ae5772`)**: `docs/superpowers/`, `docs/sketches/`, `docs/work-queue.json` DELETED (git history
  is the archive, last present at `b723bde`); `docs/specs/` for design docs; `docs/README.md` index; PLAN.md is the ONLY queue.
- Community thread + JetBrains review (P43–P48) → **M31** ifeval arm for `Qwen3.8-27B-mlx-uniform-4bit` queued.
- Pre-session untracked rows committed (`5b8f4de`, `3ea3d9c`); C46 filed.

## THE BOX QUEUE
1. **C46** pre-C28 timeout re-measurements (open-questions row): `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` hep+mbpp
   @t0.55/@t0.6 first, then the M25 pair @t0.6; full n=50 re-runs, `--sampling-profile deployed`, overlay in env,
   predictor OFF, 5-item seeded pilot sized against the nearest full-run actual (see rule below).
2. **M31** ifeval arm (~2 h). 3. M17 / D11 / M18.

## Standing rules that bit today
- A 5-item seeded pilot OVER-projects when the draw lands on heavy cores (2/5 today, 24.3 h projected vs 7.3 h actual):
  size from the pilot AND the nearest full-run actual; never gate an abort on the pilot mean alone (chain has `MBPP_SKIP_PILOT`).
- The commit-msg AND pre-commit hooks reject family shorthand in comments/docs ("the uniform-4bit sibling", "OptiQ") <!-- allow-shorthand -->
  — write the full registry name, or mark the line `allow-shorthand` when it must quote one.
- Co-resident workloads (an operator transcription job pushed swap to 11 GB) contaminate wall-clock, not tokens; log
  the window, exclude it from latency, never kill the operator's process.
- evalplus grading silently returns `acc: None` with a note when docker is down (rc=0); `compare` then reports
  "item sets differ". Check the score note before trusting an empty compare.
- zsh: `for x in $VAR` does not word-split; quote `--include='*.py'`.

## Artifacts
`$STACK_WORKDIR/m21/` (chains, logs, `k3_analysis.py --bench`, analyses, card draft, overlay);
`$STACK_WORKDIR/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/optiq_mixed` (18 GB, the served local copy of the
uploaded repo — KEEP, it is the registry override target). HF cache: `TeichAI/Qwen3.8-27B-Fable-Distill` bf16 source <!-- allow-shorthand -->
(54 GB) — no further conversion is planned (M22 is dead with M21 negative): DELETABLE on operator say-so.

**Order of resumption: this file → `docs/PLAN.md` (C46 row in open-questions, M31) → `docs/open-questions.md`.**

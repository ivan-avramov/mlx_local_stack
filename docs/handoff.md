# Handoff — 2026-09-03 18:00 (C46 LEG 1 LIVE — `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` pre-C28 timeout re-measurement; M21b CLOSED; C47 shipped)

Single box (M5 Max 64 GB). **C46 LEG 1 IS LIVE** (launched 2026-09-03 17:57, operator GO "proceed with your recs: leg 1 then
evaluate for leg 2"): chain `$STACK_WORKDIR/c46/c46_chain.py` (pid in `c46/c46.pid`, log `c46/c46.log`, `C46_STOP_AFTER_LEG1=1`),
router UP on the M21 draft-OFF overlay (`$STACK_WORKDIR/m21/bench_overlay_m21.yaml`, SESSION_MAX=2, APC absent),
`src/mlx-vlm` worktree at the stack pointer `7330d3a6` (serving path `920efc38`, ≡ the M21b arms). First C35 check OK
(`draft_kind=off`, registry sha match). Order inside leg 1: pilot (5 seeded items hep+mbpp) → hep+mbpp n=50 @`t0.55-r2`
(deployed) → hep+mbpp n=50 @`t0.6-r2` (`--temp 0.6`) → grade → `compare t0.55-r2 vs t0.6-r2` → chain EXITS. Projected 9–26 h
(converged work ~5 h + up to 20 old-DNF items at ~1 h each if they are true budget hits). Per row the log carries a
`DNF FOLLOW-UP` line (each old 'timed out' item and what it did under the 7800 s bound) — that IS the C46 deliverable.
Leg 2 (`Qwen3.8-27B-mlx-uniform-4bit` vs `Qwen3.8-27B-OptiQ-4.5bpw-mixed` @`t0.6-r2`, ~12–22 h) is a SEPARATE decision after
the leg-1 review; it underpins no live pick (the B 3rd-choice certification rests on the post-C28 `mtpoff` n=164 rows + M9).
OrbStack must be running for evalplus grading (the chain runs `open -a OrbStack` itself if `docker info` fails).

Stack PUSHED through `5788c4b`; UNPUSHED: `5a68763` (PLAN M32 row) + this checkpoint. Push needs
in-turn approval every time.
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
1. **C46 leg 1 RUNNING** (see top). Then the leg-1 review: does t0.55 still beat t0.6 on `acc_strict@81920` under the C28
   bound (O37 stake)? Then decide leg 2 (the M25 reference pair; not a live-pick dependency).
2. **M31** ifeval arm (~2 h). 3. **M32** opencode python leg for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5 (~2 h; the mixed recipe has never run an agentic leg — the sibling's 13/22 is what excludes the checkpoint from B). 4. M17 / D11 / M18.

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
`$STACK_WORKDIR/c46/` (chain, `c46.log`, per-run driver + `watch_*` logs, `mem_arms.log`, pilot/full pids, grade + compare logs).
`$STACK_WORKDIR/m21/` (chains, logs, `k3_analysis.py --bench`, analyses, card draft, overlay);
`$STACK_WORKDIR/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/optiq_mixed` (18 GB, the served local copy of the
uploaded repo — KEEP, it is the registry override target). HF cache: the `TeichAI/Qwen3.8-27B-Fable-Distill` bf16 source <!-- allow-shorthand -->
(52 GB) was DELETED 2026-09-03 18:20 (operator); re-download only if a new conversion is ever planned.

- Old-vs-new `compare` on C46 rows REFUSES by design: the old rows sit at serving path `17e0e5a7` (fork `0c1c8b17`), HEAD is `920efc38`; the verdict is new-vs-new plus the DNF follow-up. Item sets are identical (seed-0 draw), so the follow-up is paired.

**Order of resumption: this file → `docs/PLAN.md` (C46 row in open-questions, M31) → `docs/open-questions.md`.**

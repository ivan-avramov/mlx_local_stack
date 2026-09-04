# Handoff — 2026-09-03 21:20 (C46 LEG 1 DONE — O37 stands on restated evidence; box IDLE; leg 2 ruling + M31 next)

Single box (M5 Max 64 GB). **NO detached job is live** (C46 leg-1 chain exited 21:07 by design). Router UP on the M21 draft-OFF
overlay (`$STACK_WORKDIR/m21/bench_overlay_m21.yaml`, SESSION_MAX=2, APC absent; worker idle, last served
`Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit`). `src/mlx-vlm` worktree at the stack pointer `7330d3a6` (serving path `920efc38`).
OrbStack up. **C46 leg 1 landed** (this checkpoint's data commit): all 20 pre-C28 DNF items re-drawn under the C28 bound — 18 converge in
seconds, 2 are true degenerate-repetition budget hits (both at t0.6); t0.55 vs t0.6 strict 86/74 vs 86/70, budget hits 0 vs 2 per 100,
Σ wall 0.38 h vs 2.69 h → **O37 (t0.55) STANDS on the runaway tax**; the cited "82/70 vs 76/68, DNFs 14→6" is withdrawn (campaign-results
2026-09-03 entry + dated correction under the 2026-08-23 entry; registry comment corrected via the HEAD blob). Leg 1 took 3.2 h vs a
9–26 h projection — pre-C28 DNF counts over-project by construction (cascade). **Leg 2 awaits the operator's ruling** (session
recommendation: CLOSE WITHOUT RUNNING — no live pick depends on the `Qwen3.8-27B-mlx-uniform-4bit` / `Qwen3.8-27B-OptiQ-4.5bpw-mixed`
hep+mbpp t0.6 rows; note the cascade caveat instead). Chain for leg 2 exists (`$STACK_WORKDIR/c46/c46_chain.py`, run with
`C46_SKIP_LEG1`-style edit: comment out leg 1) if ruled GO, ~11–16 h revised.

Stack PUSHED through `5788c4b`; UNPUSHED: `5a68763` (PLAN M32 row), `24151f2` (handoff), the C46 leg-1 data commit, this checkpoint. Push needs
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
1. **C46 leg 2 — operator ruling owed** (recommend CLOSE without running; if GO ~11–16 h).
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

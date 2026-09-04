# Handoff — 2026-09-03 21:50 (M31 ifeval LIVE; C46 CLOSED — leg 1 restated O37, leg 2 closed under the operator's skip standard)

Single box (M5 Max 64 GB). **M31 IS LIVE** (launched 2026-09-03 21:44): chain `$STACK_WORKDIR/m31/m31_chain.py` (pid in `m31/m31.pid`,
log `m31/m31.log`), router UP on the M21 draft-OFF overlay (`$STACK_WORKDIR/m21/bench_overlay_m21.yaml`, SESSION_MAX=2, APC absent),
`src/mlx-vlm` worktree at the stack pointer `7330d3a6` (serving path `920efc38`). Order: `Qwen3.8-27B-mlx-uniform-4bit` @t0.6 pilot
(5 seeded items) → n=148 → grade → `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` @t0.3 pilot → n=148 → grade → `compare` (tune `m31` on both;
the 3.6 arm is a re-measure because its 2026-08-18 row is pre-C28 with 6 timeout DNFs and sits at serving path `17e0e5a7`). Sizing:
PLAN said ~2 h; realistic 10–12 h (base ~150–200 s/item at 20–29 tok/s; 3.6 ~84 s/item) — the pilot lines in the log size it.
`NLTK_DATA` verified under `$STACK_WORKDIR` on the driver pid (a stray `~/nltk_data` from before the redirect exists; harmless, not ours to delete).
**C46 is CLOSED**: leg 1 restated the O37 evidence (t0.55 stands on the runaway tax; 18/20 pre-C28 DNFs were a cascade); leg 2 closed
without running after verifying no pick, ranking or tune certification cites those rows (operator standard: skip only when KNOWN
not to help a pick; verification text in campaign-results 2026-09-03).

Stack PUSHED through `5788c4b`; UNPUSHED: `5a68763`, `24151f2`, `a70bf4e` (C46 leg-1 data), this checkpoint. Push needs
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
1. **M31 RUNNING** (see top). Review: prompt-level strict, pre-registered ≥5pp-deficit rule; no re-rank on its own.
1b. **M33 QUEUED behind M31 by a waiter** (`$STACK_WORKDIR/m33/waiter.sh`, pid in `m33/waiter.pid`): math500 n=100 for the three C
   candidates (PLAN M33; ~35–55 h). To put M32 first instead: kill the waiter by pid BEFORE M31 exits, run M32, then start
   `m33_chain.py` by hand (same launch recipe as M31).
2. **M32** (proposal to be drafted while M31 runs; ~2 h) opencode python leg for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5 (~2 h; the mixed recipe has never run an agentic leg — the sibling's 13/22 is what excludes the checkpoint from B). 4. M17 / D11 / M18.

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
`$STACK_WORKDIR/m33/` (chain, waiter, `m33.log`; empty until the waiter fires).
`$STACK_WORKDIR/m31/` (chain, `m31.log`, driver + `watch_*` logs, grade + compare logs).
`$STACK_WORKDIR/c46/` (chain, `c46.log`, per-run driver + `watch_*` logs, `mem_arms.log`, pilot/full pids, grade + compare logs).
`$STACK_WORKDIR/m21/` (chains, logs, `k3_analysis.py --bench`, analyses, card draft, overlay);
`$STACK_WORKDIR/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/optiq_mixed` (18 GB, the served local copy of the
uploaded repo — KEEP, it is the registry override target). HF cache: the `TeichAI/Qwen3.8-27B-Fable-Distill` bf16 source <!-- allow-shorthand -->
(52 GB) was DELETED 2026-09-03 18:20 (operator); re-download only if a new conversion is ever planned.

- Old-vs-new `compare` on C46 rows REFUSES by design: the old rows sit at serving path `17e0e5a7` (fork `0c1c8b17`), HEAD is `920efc38`; the verdict is new-vs-new plus the DNF follow-up. Item sets are identical (seed-0 draw), so the follow-up is paired.

**Order of resumption: this file → `docs/PLAN.md` (C46 row in open-questions, M31) → `docs/open-questions.md`.**

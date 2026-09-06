# Handoff — 2026-09-05 19:55 (SESSION CHECKPOINT — M33 math500 RUNNING unattended; M31/M31b/C46 closed; M34 + M35 built; queue set)

Single box (M5 Max 64 GB). **M33 IS LIVE and self-driving** (chain `$STACK_WORKDIR/m33/m33_chain.py`, pid in `m33/m33.pid`
(2625 at checkpoint), log `m33/m33.log`, launched 2026-09-05 02:58): math500 n=100 seed-0 draw, tune `m33`, three arms in order —
`Ornith-1.0-35B-mlx-uniform-4bit` DONE (acc 91.0 / strict 86.0, 6 budget hits, 4.7 h) → `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
IN FLIGHT (n=100 leg; 69/100 rows, 2 loops at 19:53; ~13 min/converged item, ~75 min/loop; ETA ~05:00 2026-09-06) →
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (pilot → 50 → 100; fast decoder, ~3–6 h) → grade → 3 pairwise compares → chain exits
(`=== M33 DONE ===`). No waiter follows it; the box goes IDLE when it ends. Router UP on the M21 draft-OFF overlay
(`$STACK_WORKDIR/m21/bench_overlay_m21.yaml`, pid 37747, SESSION_MAX=2, APC absent). `src/mlx-vlm` worktree at the stack pointer
`7330d3a6` (serving path `920efc38`) — **DO NOT bump the submodules until M33 ends** (the M34 fork commits change the serving path).
Working tree: SEVEN intentional `main_models.yaml` local-path overrides — NEVER commit (committed registry edits go via the HEAD blob).
UNPUSHED: `46aa77b`..`76dc405` (8 commits: M31/M31b data, queue update, M35 spec + adapter + fixes, this checkpoint). Forks are pushed
(mlx-vlm `420c01e1`, mlx-serve `0ccc684`). Push only on in-turn approval.

## Resume checklist (new session)
1. `pgrep -f m33_chain.py` / `kill -0 $(cat $STACK_WORKDIR/m33/m33.pid)`; `tail -5 $STACK_WORKDIR/m33/m33.log`; row counts in
   `benchmark/results/<model>/math500.m33.jsonl`. Re-arm a Monitor on `m33.log` (tail -F | /usr/bin/grep --line-buffered on
   `FATAL|WARN|ALARM|C35|PILOT SIZING|SUMMARY|SCORE|ROWS|END |DONE|Traceback`) with a pid-liveness loop and a known-positive SELFTEST
   line — Monitors do not survive a session. bench_watch daemons are launched by the chain itself.
2. When `=== M33 DONE ===`: pull `m33/compare_*.log`, write the C-menu review (acc_strict paired n=100, Holm over 3 pairs, runaway tax),
   land rows + campaign-results entry + PLAN M33 DONE; C order stays PROVISIONAL (registry comment update via HEAD blob if reordered).
3. Then the queue below, each with its own proposal, 5-item SEEDED pilot, and operator go.

Stack PUSHED through `5788c4b`; UNPUSHED: everything from `5a68763` on (C46 data, C46 closure, M33 row, M34 spec + build, PARAMS fix, handoffs). Push needs
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
1. **M33 RUNNING** (see top). After it: submodule bumps (`chore(stack): bump src/mlx-vlm -> 420c01e1`, `src/mlx-serve -> 0ccc684`) BEFORE any new arm, so every later row carries the new serving-path hash consistently.
1b. (done) M31 finish → M31b → M33 were chained by `$STACK_WORKDIR/m33/waiter3.sh`** (pid in `m33/waiter3.pid`; waiters 1–2 killed): after M31 exits →
   `m31/m31_finish.py` (resumes the 3.6 arm if the chain's 20 h driver bound cut it short — projected finish ≈ the bound; re-grades + re-compares; no-op if complete) → `m31/m31b_chain.py` = ifeval arm for `Qwen3.8-27B-OptiQ-4.5bpw-mixed` @t0.6, tune `m31`, same
   seed-0 draw, compares vs both M31 arms (operator 2026-09-04: the M25 tie deserves the same test; ~5 h) → then `m33_chain.py`
   (math500 n=100 × 3 C candidates, ~35–55 h). To put M32 first: kill waiter2 by pid BEFORE M31 exits and re-chain by hand.
2. **M32** opencode python leg for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` @t0.5 (~2 h; proposal to draft).
3. **M24 medium arm** (revived 2026-09-05): `Qwen3.8-27B-mlx-uniform-4bit` @t0.6 `reasoning_effort=medium`, tune `t0.6-effmed`, M21b recipe + opencode python leg; pre-registered read + the truncation confound in PLAN (~12 h).
4. **M34 OFAT** on `Ornith-1.0-35B-mlx-uniform-4bit` (needs the submodule bumps + an M34 overlay entry first; ~15–20 h).
5. **M35** dsh smoke + one python leg (~3 h box). Adapter BUILT (`4cf25d9` + `9e56a01`, verifier-fixed); smoke = `run_dsh_probe.py --model Qwen3.8-27B-mlx-uniform-4bit --items affine-cipher --lang python --tune m35` with `MLX_SERVE_CONFIG` on the driver, then a 5-item SEEDED pilot before the 22-item leg; must confirm: model name on the wire, file_changed via read→write, no FS_NOT_OBSERVED refusals, gate ticks vary on a long item, no web/subagent tools on the wire.
6. M17 / D11 / M18.

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

## M34 BUILT 2026-09-03 (box-free; unpushed in three repos)
Layer-scoped expert-budget expansion (spec `docs/specs/m34-moe-expert-expansion.md`). Fork `../mlx-vlm` main: `b95130c9` (feature)
+ `420c01e1` (verifier fixes) — 2 ahead of origin. `../mlx-serve` main: `0ccc684` — 1 ahead. Stack: `674499c`, `0e1a29b`, `3493c34`
(PARAMS drift-guard fix). NOT YET: fork pushes → `chore(stack): bump src/mlx-vlm` + `src/mlx-serve`; registry `moe_expand:` field on an
M34 overlay entry; the OFAT (after M33). Verifier scripts kept at `$TMPDIR/m34verify/` (re-run `v3_identity.py` after any routing edit).

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

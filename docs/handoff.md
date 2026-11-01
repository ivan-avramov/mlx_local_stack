# Handoff — 2026-11-01 (session 13, IN PROGRESS: Wave 2 legs 1–8 running; v8 frozen; nothing pushed yet)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C266, P585, C265, P584, P583, C264, P581–P582, C263,
P579–P580, C262, P578–P577, P576, C261, P570–P575, P569, P568–P563), and spec `docs/specs/p426-b2-tg1-wave2.md` §1, §7, §9, §10, §16.8.
Model names: FULL registry names only. Review rounds: 3 per artifact (AGENTS.md).

## FIRST — check Wave 2

1. The sequencer (`bench.p426_wave2 run`, launched 2026-11-01 05:37 UTC under `nohup`, pid 16891 at launch) writes
   `$STACK_WORKDIR/p426/wave2/sequencer.stdout` and `sequence.json`; resume = the same command (below). Exit codes: 0 done, 1 stopped
   (leg / gate / pair / drift), 2 refused, 3 overrun pause, 4 harvest failure — none loses a leg. A stop is the operator's decision.
2. Legs: 1–2 pilots → pilot gate + timeout amendment (automatic) → 3–4 s1 off/on → 5–6 s2 on/off → 7–8 reload on/off (≈ 13 h).
   Each leg's watcher must be alive (`<leg>.a1/watch.jsonl` ticks every 300 s; P547).
3. Harvests land in the main checkout `benchmark/results/p426/wave2/<attempt>/` (uncommitted until committed as `data(bench)`) and the
   evidence stage `$STACK_WORKDIR/p426/wave2/scratch/evidence`.

Resume command (from the main checkout; relative `PYTHONPATH` so each watcher imports its own worktree):
`set -a; . "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"; set +a; PYTHONPATH=benchmark nohup .venv-bench/bin/python -m
bench.p426_wave2 run --record-dir $STACK_WORKDIR/p426/wave2/records --worktree-off $STACK_WORKDIR/worktrees/stack-p426-off --worktree-on
$STACK_WORKDIR/worktrees/stack-p426-on --out-base $STACK_WORKDIR/p426/wave2 --historical-walls
benchmark/results/p426/wave2/historical_walls.json >> $STACK_WORKDIR/p426/wave2/sequencer.stdout 2>&1 </dev/null &`

## State — 2026-11-01

- **v8 frozen** (C266): `$STACK_WORKDIR/p426/wave2/records/v8_base.json` (`af0711cf…`): OFF `5fd3c972` (`main` `192d1c71` minus C244's
  registry + seeding-test hunks, P564), ON `2a173f8b` (tree == `main`), settle bound 2123.7 s, pilot deadline 11,469 s, prompt date
  `Fri Oct 30 2026`, build inputs `$STACK_WORKDIR/p426/wave2/build_inputs-20261101a.json` (gate PASS `stack-5fd3c972…`), walls
  `benchmark/results/p426/wave2/historical_walls.json` (P566). Rehearsal `20261101a` (manifest `2bfffbd3…`): R1 VALID ×2 + dossier PASS,
  R2 INVALID (injected), R3 VALID `kill_inflight_failed`.
- **B2 live bugs found and fixed this session** (each red-first; reviews in `docs/reviews/p579-p580/`, `p581/`, `p583/`, `p585/`):
  P578 worktree_state read the submodule HEAD; P579 two opencv wheels own `cv2/*`; P580 console-script shebangs; P581 worker argv shebang
  token; P582 TMPDIR harvest rules; P583 metallib via descriptor; P584 R3 stall-kill = the real `stalled` gate; P585 psutil SystemError
  in the process guard (v3 + round-3 fix). P576 (rehearsal default main root) worked around with `--main-root`, fix pending.
- **C258 crossover** (P568 → P577 C262 option (a)): the `run_capacity` instrument failed its `Ornith-1.0-35B-mlx-uniform-4bit` 256K
  anchor (−1.1% vs C249's −8.7%; rows committed, void); next = a fork dev-only `qualify.py --prompt-tokens` + `--max-output-tokens`
  (request override recorded; output length fixed at 2048 for comparability, 256 for the length effect), test-first + one cold review,
  then 128K / 192K ABBA per C258 entry — in quiet windows only.
- **P503** (C261): proposals P570–P575 approved; build in the first quiet window (never during a leg).
- **P569**: the C260 cleanup lost P499's rows / worker log and the T3 smoke worker logs; the cleanup inventory was not filed.

## Worktrees / scratch (each with its resolution)

- `$STACK_WORKDIR/worktrees/stack-p426-off`, `stack-p426-on` (branches `p426-off`, `p426-on`): Wave 2 arms — keep until Wave 2 is
  harvested; archive the two arm commits to `origin` as `archive/p426-wave2-{off,on}` at the push (P567, approval then), then remove.
- `$STACK_WORKDIR/worktrees/stack-c258x-off` (branch `c258x-off`): the crossover's all-OFF registry — keep for P577; remove after.
- `$STACK_WORKDIR/p426/rehearsal/{20261030,20261031,20261031b,20261031c,20261031d,20261101a}` + `manifest-*.json` + `main-clone-*`:
  rehearsal attempts (only `20261101a` binds v8); harvest the `20261101a` stage to `evidence` with Wave 2, the rest are refusal records
  (file a summary, then delete the clones).
- `$STACK_WORKDIR/c258x/` (crossover block logs; the smoke block log carries a charger serial in its power lines — scrub before any
  harvest), `$STACK_WORKDIR/p426/historical/` (harvested, `c42bca0c`), `$STACK_WORKDIR/scratch/evstage-20261030-p566` (published).

## Push (one, at the end of the session, operator approval)

`main` (docs / fixes / data: level full needs a PASS gate on its tip), `evidence` (`c42bca0c` + the Wave 2 stage: data-only), the arm
archive branches. Read every gate verdict before the push; never chain them (P541).

## Rules learned (session 13)

- B2's box ops had only fake-ops tests: a read-only shakedown of every real box op against the real arms before a launch found four
  bugs at once; do it before any first live run.
- A spec's injection must be checked against the real mechanism (P584: a lowered silence limit never fires on a healthy item).
- Never mutate a library's shared objects to change its behaviour (P585 v2 broke psutil's `oneshot` / cache everywhere).
- A narrowed fix is a scope change: say so in the proposal, not in a status line (P585 v1).
- Background shells here may not expand globs: build pytest file lists in Python (`glob.glob`).
- A directory is deleted only when a manifest lists its files; harvest a cleanup's own inventory first (P569).

Next decision id C267; discussion ids continue from P586.

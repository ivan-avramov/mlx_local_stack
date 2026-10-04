# Handoff — 2026-10-04 (19:30 UTC): M55 polyglot gap COMPLETE and LANDED; daily driver UP; push pending operator

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (the only queue) and
`docs/open-questions.md` (C109 ruled, C110 ruled: wait-and-watch). Results: `docs/campaign-results.md` 2026-10-04 (M55) and 2026-10-03
(M54 chain 4). History: `docs/lab-notebook.md` 2026-10-03/04. Specs: `docs/specs/m55-polyglot-gap.md`, `docs/specs/m54-agentbench-os.md`.

## State of the world

- **Git:** pushed through `7baa6dc`. NOT pushed: everything since (M54 chain 4 landing, C109/C110 rulings, M55 queue + landing, scrubber fix).
  **Push only on the operator's word** ("we push after the results are done" — results are done; awaiting the word).
- **Daily driver is UP** (router pid 74568, `MLX_VLM_CACHE_SESSION_MAX=2`, APC absent, OWUI healthy). No lean router, no benchmark processes,
  0 orphan shells. Battery 100 %, adapter 140 W. Scratch dir is `$STACK_WORKDIR/scratch/octmp.noindex` with a symlink at `octmp`.
- **M55 landed:** rows `benchmark/results/<model>/opencode_<lang>.m55.s{1,2}.{jsonl,manifest.json}` (18 + 18), report
  `benchmark/results/m55_polyglot_gap_report.md`, campaign-results 2026-10-04, README rows (first-pick coverage gap retired), PLAN M55
  COMPLETE, notebook. Workdir keeps everything under `$STACK_WORKDIR/m55/` (RUNLOG, per-leg logs, pilot, scripts).
- **Picks unchanged.** No ladder change proposed (first pick leads Rust/Java and the 66-item total; second pick's JavaScript edge inconclusive).
- **Harness:** `run_opencode_probe._scrub_pii` now scrubs the whole-word login name (`$USER`) — `ls -l` owner columns leaked it; test added.

## Rules learned (also in notebook / AGENTS.md)

- `pgrep -f` liveness checks must use self-safe patterns (`mlx_vlm[.]server`): a monitor whose command line contains the pattern is a false "alive".
- Spotlight: exclude grading scratch trees with the `.noindex` directory suffix; the probe's default scratch should move there permanently (todo below).
- Laptop power gate (AGENTS.md): 140 W / 28 V and battery > 20 % before/during latency captures.
- Determinism = one loaded-model lifetime; opencode loops are unseeded → pilot gate is pass-identity; k=2 sessions for every agentic chain (C109).

## Pending

1. **Operator:** push.
2. Small follow-up (no GPU): make the probe's scratch default `$STACK_WORKDIR/scratch/octmp.noindex` in code/config so the symlink is not load-bearing.
3. M56 LiveCodeBench rolling window: PARKED (C110 wait-and-watch) — re-check on each LiveCodeBench release for a window starting after 2026-06.
4. Declined earlier: aider_polyglot full corpus via aider, QuixBugs, quantevallab2.0; C108 follow-up closed.

Next decision id C111; discussion ids continue from P25.

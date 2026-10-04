# Handoff — 2026-10-04 (21:00 UTC): M55 landed and PUSHED; proposals reviewed (flash attention → discuss next session); daily driver UP

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (the only queue) and
`docs/open-questions.md` (C109 ruled, C110 ruled: wait-and-watch). Results: `docs/campaign-results.md` 2026-10-04 (M55) and 2026-10-03
(M54 chain 4). History: `docs/lab-notebook.md` 2026-10-03/04. Specs: `docs/specs/m55-polyglot-gap.md`, `docs/specs/m54-agentbench-os.md`.

## State of the world

- **Git:** pushed through `bd2823d` (2026-10-04, operator's word). Tree clean after this handoff commit.
- **Stack is DOWN by operator instruction (2026-10-04): do NOT auto-start `runserver.sh`; the operator runs it when they want it.**
  `scripts/stack_stop.sh` applied: :8000 free, no router/worker/task-model processes, 0 orphan shells. Lean benchmark routers are still
  started as a measurement requires. Scratch dir is `$STACK_WORKDIR/scratch/octmp.noindex` with a symlink at `octmp`.
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

1. **Next session (operator): dedicated discussion of `docs/proposal-flash-attention.md`** — reviewed 2026-10-04 (verdict: pick up as M57;
   measured 144 → 46 ms per full-attention layer at the first pick's prefill shape with `force_fused=True`; the memory benefit is NOT
   measured, only time). `docs/proposal-image-gen.md` reviewed and stays deferred. Nothing queued in PLAN for either yet.
2. DONE 2026-10-04: probe scratch default is `<STACK_WORKDIR>/scratch/octmp.noindex` in code (`OPENCODE_PROBE_SCRATCH` overrides); the
   workdir symlink `scratch/octmp → octmp.noindex` can be removed at leisure. Pushed through `bd2823d`+.
3. M56 LiveCodeBench rolling window: PARKED (C110 wait-and-watch) — re-check on each LiveCodeBench release for a window starting after 2026-06.
4. Declined earlier: aider_polyglot full corpus via aider, QuixBugs, quantevallab2.0; C108 follow-up closed.

Next decision id C111; discussion ids continue from P25.

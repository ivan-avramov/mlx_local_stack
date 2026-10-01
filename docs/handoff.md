# Handoff — 2026-10-01: M54 AgentBench OS built, reviewed, chain 1 complete; chain 2 (pty harness) running

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (the only queue) and
`docs/open-questions.md` (decisions; C107 holds the M54 rulings and amendments). Spec + pre-registered acceptance
criteria: `docs/specs/m54-agentbench-os.md`. Results narrative: `docs/campaign-results.md` 2026-10-01. History:
`docs/lab-notebook.md` 2026-10-01.

## State of the world

- **Git: NOT pushed** — stack main at `815af79` + later data/docs commits this session (see `git log 70a61a7..`). Forks unchanged.
- **Stack is DOWN; a LEAN ROUTER is up** for the M54 arms: router pid 70408 on :8000, `MLX_SERVE_CONFIG=$STACK_WORKDIR/m54/overlay_m54_draft_off.yaml`
  (every `draft_*` stripped from the registry of record; sha `81fa0c15…`), `MLX_VLM_CACHE_SESSION_MAX=2`, APC absent. The daily driver
  (`runserver.sh`, OpenWebUI) was stopped with `scripts/stack_stop.sh` at 04:52 PDT. **Restore the daily driver after chain 2:**
  `scripts/stack_stop.sh` (kills the lean router) then `./runserver.sh` (or `/mlx start`).
- **Picks unchanged.** No serving config changed. Registry of record untouched.
- **Chain 2 is RUNNING** (`$STACK_WORKDIR/m54/arms_909b1e0/run_arms.py`, runner pid in `runner.pid`, per-arm `driver.log`/`watch.log`,
  `RUNLOG.md` with RESULT lines): five arms in order first pick, second pick, `Ornith-1.0-35B-mlx-uniform-4bit`,
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`; harness `909b1e0` (pty shell), ~4 h.
  Pinned worktrees under `$STACK_WORKDIR/m54/wt-*` (remove with `git worktree remove` when done).
- Docker images `local-os/{default,packages,ubuntu}` built from `ubuntu:24.04@sha256:11dc1ccb…`; exclusions artifact rule v2
  (`benchmark/corpora/agentbench_os_v1.exclusions.json`, 142 gradeable) — committed once `scripts_root` is relative (task with the implementer).

## DONE this session

- M54 built from the spec by a Sonnet implementer; 16 cold-review rounds (Claude reviewer ×12 with real-bash/pty probes and
  mutation testing, Codex gpt-6-astra ×8); every round's findings in `$STACK_WORKDIR/m54/codex_review_*.md` and the agent reports.
- Live pilot 3/5 (first pick); two shakedown arms on `1feba7c`; **chain 1 on `b43c8e5` complete** (table in campaign-results):
  dense Qwen checkpoints tie at 0.61–0.62, `Ornith-1.0-35B-mlx-uniform-4bit` 0.549, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` 0.415;
  rows `benchmark/results/<model>/agentbench_os.v1.chain1.*`, report `benchmark/results/agentbench_os_compare_chain1.md`.
- Tools: `bench/run_agentbench_os.py` (driver, `--prepare`, M50/C106), `bench/agentbench_adapter.py`, `bench/agentbench_watch.py`
  (5-min daemon, calibrated busy/idle), `bench/agentbench_compare.py` (paired report; refuses mixed harness/shell_mode),
  `scripts/build_agentbench_images.sh`. Suite ~2520 tests.

## Rules learned this session

- Upstream AgentBench OS shell is `tty=True` interactive bash (AgentRL `create_shell`); a non-tty shell dies on a model syntax error.
  Upstream strips five escape patterns before the model sees output (`task.py` `Container.execute`).
- Upstream grades check-tasks by running the reference in the task's OWN container → randomized-init tasks are gradeable; an exclusion
  rule that compares two fresh containers over-excludes (11 tasks).
- The first pick's native16 KV at full prealloc plus docker containers runs the box at 84–87 % RAM; one router 500 at 96 %.
  The 4-bit-KV models never warned. Keep the box quiet for native16 arms.
- zsh: a failed glob aborts the whole command line (monitors died silently); `${=var}` for word-splitting.
- The C35 provenance tests read the LIVE worker; they fail by design while a draft-off overlay arm is resident.

## Pending

1. Chain 2 completion → compare report (chain 2 only) → harness-sensitivity note (chain 1 vs 2, by hand, never pooled) → campaign-results/README update → restore daily driver.
2. Commit the chain-1 rows (blocked on a narrow piicheck exemption for guest-OS `/home/<name>/` paths in agentbench rows) and the exclusions artifact (relative `scripts_root`).
3. Decision for the operator: chain 2 becomes the record if its results agree; if they differ materially, the pty harness is the faithful one.
4. Push: operator's call (nothing pushed this session).

Next decision id C108; discussion ids continue from P5.

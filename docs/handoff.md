# Handoff — 2026-10-02: M54 AgentBench OS COMPLETE (chain 3 = record); daily driver restored; nothing pushed

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (the only queue) and
`docs/open-questions.md` (C107 closed, C108 ruled). Results: `docs/campaign-results.md` 2026-10-02 (record) and
2026-10-01 (non-tty sensitivity run). History: `docs/lab-notebook.md` 2026-10-01/02. Spec: `docs/specs/m54-agentbench-os.md`.

## State of the world

- **Git: NOT pushed.** Stack main at `3807998` (operator said: push at wrap-up, on their word). Forks unchanged. Tree clean.
- **Daily driver is UP** (restored 11:10 UTC via `runserver.sh`): router pid 18697 on :8000, `MLX_SERVE_CONFIG=main_models.yaml`,
  `MLX_VLM_CACHE_SESSION_MAX=2`, APC absent, OpenWebUI + SearXNG healthy. No serving config changed; registry of record untouched.
- **Picks unchanged.** M54 proposes no ladder change (see Results).
- Pinned worktree kept: `$STACK_WORKDIR/m54/wt-df3b65c` (the record's harness); all others removed. Run artifacts, review reports
  (`codex_review_1..8.md`), run logs (`pilot/RUNLOG.md`) and all chain rows live under `$STACK_WORKDIR/m54/`.
- Docker images `local-os/{default,packages,ubuntu}` (pinned `ubuntu:24.04@sha256:11dc1ccb…`) remain; exclusions artifact rule v2 committed.

## Results (M54, AgentBench OS `os-std`, 142 tasks, draft OFF, deployed sampling, thinking ON)

Record = chain 3, harness `df3b65c` (pty shell faithful to upstream): `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 0.620 (2 runaways,
5× tokens), `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` 0.592, `Qwen3.8-27B-mlx-uniform-4bit` 0.592, `Ornith-1.0-35B-mlx-uniform-4bit`
0.535, `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` 0.423. Picks tie exactly; first pick at half the tokens and a quarter of the
runaway share. Chain 1 (`b43c8e5`, non-tty) agrees on ranks (sensitivity run). Chain 2 void (sentinel defect). Report files:
`benchmark/results/agentbench_os_compare_chain{1,3}.md`.

## Harness (committed on main, latest `aac939b`)

`bench/run_agentbench_os.py` (driver; `--prepare`; M50/C106; resume identity), `bench/agentbench_adapter.py` (pty shell, marker via
PROMPT_COMMAND, whole-script rounds, escape stripping, process-group cleanup), `bench/agentbench_watch.py` (5-min daemon, calibrated
busy/idle), `bench/agentbench_compare.py` (paired report; refuses mixed harness/shell_mode), `bench/agentbench_live_smoke.py`
(docker live gate), `scripts/build_agentbench_images.sh`, `scripts/sweep_orphan_shells.sh`. Suite 2560 green. 20 cold-review rounds.

## Rules learned (also in notebook)

- Upstream's shell is an interactive tty; tty-reading programs eat anything queued on stdin → the marker must come from bash itself.
- Whole-script rounds need `eval` of a quoted heredoc (a brace group double-fires on a syntax error).
- Never close a pty fd while a thread may write to it; pty throughput ~2 MB/s under load.
- Real-bash test shells leak on kill/alarm → process groups + finalizers; 71 orphans once pushed load to 92 and halved decode.
- Retained native16 KV sessions at full prealloc (~16 GB each) cause router 500s; bench routers use session max 1 (C108).
- Before every chain: live smoke, pilot twice, byte-identical rows.

## Pending

1. Operator: push (all commits through `3807998`).
2. Latency per task on this axis is contaminated by the load incident for some arms; re-measure on a quiet box if ever cited.
3. Future M54 runs: harness ≥ `aac939b`, one chain, pilot-twice gate; consider a pressure-aware session eviction in the fork (C108 follow-up).

Next decision id C109; discussion ids continue from P8.

# Handoff — 2026-10-02 (checkpoint 23:55 UTC): M54 record landed and PUSHED; chain 4 CLEAN CAPTURE RUNNING on the lean router; daily driver DOWN

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (the only queue) and
`docs/open-questions.md` (C107 closed, C108 ruled). Results: `docs/campaign-results.md` 2026-10-02 (record) and
2026-10-01 (non-tty sensitivity run). History: `docs/lab-notebook.md` 2026-10-01/02. Spec: `docs/specs/m54-agentbench-os.md`.

## State of the world

- **Git:** pushed through `7baa6dc` (operator, 2026-10-02). One later commit NOT pushed: `886b78d` (C108 follow-up closed). Tree clean.
- **CHAIN 4 (clean latency capture) IS RUNNING** — the daily driver is DOWN for it. Lean router pid 90462 on :8000,
  `MLX_SERVE_CONFIG=$STACK_WORKDIR/m54/overlay_m54_draft_off.yaml` (sha `81fa0c15…`), `MLX_VLM_CACHE_SESSION_MAX=1`, APC absent.
  Runner `$STACK_WORKDIR/m54/arms_aac939b/run_arms.py` (pid in `runner.pid`; nohup — survives the Claude session), harness
  `aac939b` from worktree `$STACK_WORKDIR/m54/wt-aac939b`, five arms in the standard order, per-arm `driver.log`/`watch.log`,
  `RUNLOG.md` with RESULT lines and `ALL ARMS COMPLETE` at the end. Started 23:00 UTC; arm 1 was at ~125/142 at checkpoint;
  expect ~4 h more (the `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` arm carries two ~85-min runaways). Watchers are per-arm daemons
  spawned by the runner (they survive too). **The Claude-side Monitor loops do NOT survive a session — re-arm a 5-min
  reader of `watch.log` SUMMARY/ALARM lines + `uptime` + the orphan-shell count in the new session.**
  Purpose: chains 1 and 3 have poisoned wall-clock/rate numbers (71 orphaned test shells, load 92, plus a desktop-activity
  window at 23:51 UTC noted in `pilot/RUNLOG.md`); chain 4 is the only chain whose latency is citable. acc/tokens should
  reproduce chain 3 (same seeds, same protocol).
  **When it finishes:** `scripts/stack_stop.sh` → `./runserver.sh` (daily driver back), run `bench.agentbench_compare` on the
  five `arms_aac939b` rows (see the chain-3 command in the notebook), land rows as `agentbench_os.v1.chain4.*` under
  `benchmark/results/` (scrub `$STACK_WORKDIR`/`$STACK_REPO`/`$HOME` placeholders as for chain 3), update campaign-results
  (latency/rate columns now citable; acc/tokens cross-check vs chain 3), README evidence rows, PLAN M54 row, notebook.
- **POWER INCIDENT 2026-10-02 23:04–23:50 UTC (found at session restart, 2026-10-03 00:00 UTC):** the laptop lost mains, throttled at 10 % battery
  (23:08 UTC), hibernated at 1 % (23:14:57) and woke on AC at 23:50:08. Router pid 90462, runner, driver and watcher all survived; no reboot.
  Arm 1 (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`) rows 107–142 ran throttled (16–17 tok/s vs 25–26 clean; row 128 straddled the
  hibernate) → its latency is NOT citable and the arm must be re-run on the same router session. acc/tokens vs chain 3: 0.620 vs 0.592,
  4 pass flips, 55 rows differ in tokens from row 1 on = cross-restart nondeterminism, not the incident. Arm 2 started 23:57 UTC still ~11 %
  slow (26 vs 29.4 tok/s chain-1 clean reference) with the battery charging; the runner continues as the recovery instrument — any arm with
  rows below its clean reference is re-run after arm 5. Details: `$STACK_WORKDIR/m54/pilot/RUNLOG.md` 2026-10-03T00:02Z.
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

1. Chain 4 completion + landing (above). Then push (`886b78d` + the landing commits) on the operator's word.
2. **P17 awaiting operator decision:** adopt EvoEval (`difficult` + `subtle`, frozen, execution-graded) as the coding
   de-saturation axis — LiveCodeBench rejected for the ladder because a frozen window loses contamination resistance.
   Neither B pick has a LiveCodeBench row today (P14 verified). If approved → queue as M55 in PLAN with pre-registered ACs;
   build via the M54 funnel (Sonnet implementer from the spec, cold reviews by a Claude reviewer and Codex `gpt-6-astra`).
3. Declined from the quanteval question: aider_polyglot (we run the full corpus via opencode), QuixBugs (saturated),
   quantevallab2.0 (proprietary). C108 follow-up closed: no pressure-based session eviction (operator).
4. Reviewer residuals accepted as low-severity (documented in campaign-results/spec): job control + readline completion off in the
   shell; marker forgeable only by reading `$PROMPT_COMMAND`; eval wrapper depends on `cat` on PATH.

Next decision id C109; discussion ids continue from P8.

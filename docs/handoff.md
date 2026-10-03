# Handoff — 2026-10-03 (06:30 UTC): M54 chain 4 landed; C109 ruled; M55 polyglot gap + M56 LiveCodeBench queued; daily driver UP; push pending operator

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (the only queue) and
`docs/open-questions.md` (C109 RULED 2026-10-03). Results: `docs/campaign-results.md` 2026-10-03 (chain 4 latency + re-sample),
2026-10-02 (acc record = chain 3). History: `docs/lab-notebook.md` 2026-10-03 (power incident). Spec: `docs/specs/m54-agentbench-os.md`.

## State of the world

- **Git:** pushed through `7baa6dc`. NOT pushed: `886b78d` (C108 follow-up), `f520a56`, `b818df2` (incident checkpoints) and this session's
  landing commits (chain 4 rows + docs). **Push only on the operator's word.**
- **Daily driver is UP** (`runserver.sh` pid 40615, router pid 40777, `MLX_VLM_CACHE_SESSION_MAX=2`, APC absent, OWUI healthy). No lean router.
  No benchmark processes. 0 orphan shells. Battery 100 %, adapter 140 W.
- **M54 chain 4 landed:** rows `benchmark/results/<model>/agentbench_os.v1.chain4.*` (arms 1–2 from `$STACK_WORKDIR/m54/arms_aac939b_redo/`,
  arms 3–5 from `arms_aac939b/`), report `benchmark/results/agentbench_os_compare_chain4.md`. Latency per task is now citable (first pick
  18.5 s, second pick 29.6 s, `Ornith-1.0-35B-mlx-uniform-4bit` 14.2 s, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 35.5 s,
  `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` 12.2 s). Acc record stays chain 3; chain 4 acc is a same-harness re-sample (4–6 flips/arm).
  Superseded first-pass arm 1–2 rows stay in `arms_aac939b/` (power-incident contaminated latency; repeatability sample only).
- **Picks unchanged.** No ladder change proposed (campaign-results 2026-10-03).
- Workdir keeps: `wt-aac939b`, `wt-df3b65c` worktrees; `arms_aac939b`, `arms_aac939b_redo`, earlier chains; `launch_redo.sh`, `run_arms_redo.py`,
  `land_chain4.sh`, `pilot/RUNLOG.md` (incident log with timestamps).

## Incident summary (full: notebook 2026-10-03)

Laptop lost mains during arm 1: macOS throttled decode ~35 % at 10 % battery, hibernated at 1 % (23:15–23:50 UTC), and after the wake the
MagSafe link sat at 100 W / 20 V (7–10 % slower on identical items) until re-plugged at 00:48 UTC. Arms 1–2 re-run on the same router session
after arm 5 via an unattended precondition-checked launcher. New AGENTS.md rule: `pmset -g ac` = 140 W / 28 V and battery > 20 % before/during
any latency capture; monitors print both every tick.

## Findings this session

1. Runaway tax is session-stochastic (`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`'s two chain-3 runaways did not recur; turn-cap share did) → **C109 open**.
2. Seeded determinism = one loaded-model lifetime (reload on the same router pid broke byte-identity) → `docs/metrics.md` + AGENTS.md updated.
3. macOS tooling traps: bash 3.2 (no `declare -A`), `wc -l` pads, `grep -E` has no lookahead.

## Pending

1. **Push** (`886b78d` … this session's commits) — on the operator's word only.
2. **M55 polyglot gap: CHAIN RUNNING since 2026-10-03 08:07 UTC** on lean router pid 86904 (draft-OFF overlay, session max 1, APC absent;
   daily driver DOWN). Runner `$STACK_WORKDIR/m55/run_m55.py s1 s2` (pid in `runner.pid`, nohup; leg-resumable: skips legs with 22 rows;
   `RUNLOG.md` ends with `ALL LEGS DONE`), order s1 → s2, per session first pick → second pick → `Ornith-1.0-35B-mlx-uniform-4bit`,
   langs rust/java/javascript, out `m55/s{1,2}/<model>.opencode_<lang>.jsonl`. Pilot: 5/5 pass on pass A, 4/5 pass-identical on pass B
   (AC2 amended — opencode loop is not byte-deterministic), wall mean 379 s / max 636 s → first pick ≈ 7 h per session; whole chain ≈ 40 h
   (C37 means for the baselines). Monitor every 5 min: RUNLOG END lines, adapter 140 W, battery, orphans, worker busy. On completion:
   `scripts/stack_stop.sh` → `./runserver.sh`; then land rows under `benchmark/results/<model>/opencode_<lang>.m55.s{1,2}.jsonl` (scrub),
   per-language paired report, README/campaign-results/PLAN/notebook. (Original queue entry:) spec `docs/specs/m55-polyglot-gap.md` (pre-registered ACs). Next step: lean router on the
   draft-OFF overlay (session max 1), 140 W + battery check, 5-item seeded pilot ×2 byte-identical on the loaded instance, then the 3-model × 2-session
   chain (~12 h). No build needed (M9 harness + grading containers).
3. **M56 LiveCodeBench rolling window: PARKED** (eligibility count = 0: newest release v6 ends Apr 2025; candidates trained to ≥ May 2026).
   **C110 RULED (operator 2026-10-03): wait and watch** — re-check on each LiveCodeBench release; queue M56 at ≥100 post-2026-06 problems.
   EvoEval demoted to optional diagnostic.
4. C109 RULED (open-questions): k=2 sessions for every agentic chain; runaway flags split; no pooled interval. AGENTS.md + metrics updated.
5. Declined earlier: aider_polyglot full corpus via aider, QuixBugs, quantevallab2.0; C108 follow-up closed.
6. Reviewer residuals accepted as low-severity (job control + readline completion off; marker forgeable only via `$PROMPT_COMMAND`; eval wrapper needs `cat`).

Next decision id C111; discussion ids continue from P25.

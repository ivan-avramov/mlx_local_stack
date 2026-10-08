# Handoff — 2026-10-08: M59 COMPLETE (opencode 2.x re-baseline of the two B picks, stall re-run, C137 resolved); C139 awaits the operator; stack STOPPED

THE one handoff. Read this, then `docs/PLAN.md` (M59 row) and `docs/open-questions.md` (C139 OPEN; C138 OPEN; C137 RESOLVED; C136
addendum). Results: `docs/campaign-results.md` 2026-10-08; history: `docs/lab-notebook.md` 2026-10-07/08. Artefacts:
`$STACK_WORKDIR/m59/` (M59_REPORT.md + `m59_report.py`, RUNLOG.md, `run_m59.py`, `mem_watchdog.py`, `s1/`, `s2/`, `stallprobe/`,
`archive/`, `c137/`).

## State of the world

- **Stack is STOPPED**, box idle, no watchdog or runner alive. Restart = `./runserver.sh` (operator).
- Stack `main` = this commit; `origin/main` = `c889661` (**not pushed**; operator: "we push later"). Fork `58eb241b` pushed, CI green.
- **M59 done:** Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed Python 21/22, 20/22, Go 20/22 ×2; Qwen3.8-27B-mlx-uniform-4bit Python
  20/22 ×2, Go 18/22 ×2 (rows `benchmark/results/*/opencode_v2_*.m59.*`). Every head-to-head and scaffold-delta interval includes 0;
  README evidence updated, no order change. P182: 14/18 stalls converted at 48K tokens; the 16K window under-scored the second pick
  more (7 vs 3 window-attributable conversions) → C139.
- Operator-only: delete `ts.md` and the fork `f1-sync` worktree + `sync/upstream-v0.6.15` branch (sandbox denied); push go.

## Queue, in order

1. **C139 (operator):** (a) v2 allowance 48K tokens — recommended; (b) re-record M59 at 48K (≈ 20 h box) — recommended; (c) keep 16K.
   If (a)+(b): set `DEFAULT_FIRST_WRITE_TOKENS = 48000` in `run_opencode_probe_v2.py` (test first; spec P153 + README), arm
   `mem_watchdog.py` for the run, launch `run_m59.py chain s1 s2` with session-tagged outputs (new suffix, e.g. `.w48k`) so the 16K
   record stays intact.
2. **C138 proposal** (probe interruption safety, resume-across-instances, in-probe memory cap replacing the watchdog).
3. Push when the operator says. Blind-judge agent canary in a new session. Candidates not queued unchanged.

## Rules learned (this session)

- A model-written loop can exhaust host memory through opencode's shell tool (opencode leaves timed-out commands running); arm the
  memory watchdog for every unattended run until C138 lands.
- Re-running items with the same seed separates "the gate cut it" from "run variance" only by wall time vs the original window — report
  both kinds; only window-attributable conversions measure the gate's cost.
- Estimates for runs with long per-item windows must budget the window per re-stalling item, not the typical item time.
- Anything opencode can print into its prompt must be stable per item, never per run: scratch dir name, TMPDIR, file mtimes; the date is
  a one-day window (`prompt_date`). Diff per-request `prompt_tokens` in the worker log to locate a leak before blaming the server.
- The lean worker logs to stdout unless `MLX_VLM_LOG_FILE` is set (runserver sets it); set it in every lean start that an instrument reads.
- A draft-OFF overlay must also drop `mtp_verify_scan` (it requires `draft_kind: mtp`).
- Kill runners by process group: a killed runner left its gate child alive, which overwrote the A4 receipt of the next attempt.
- Suites must run with the stack down and without `STACK_WORKDIR` exported.
- opencode 2.0.20 sometimes emits the final `step_finish` (the capture never saw it); a mock capture is necessary, not sufficient.
- Codex workers stop and ask when a ruling is needed; answer in a follow-up prompt file, keep the `.rc` launcher.

Next decision id C138; discussion ids continue from P175.

# Handoff — 2026-10-08: M59 COMPLETE; C139(a) 48K default landed; C140 RCA (1.18 vs 2.x) recorded; C141 web-access design owed; superpowers uninstalled; stack STOPPED

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
  more (5 vs 2 window-attributable conversions, by first-write time; corrected from 7 vs 3) → C139.
- Operator-only: delete `ts.md` and the fork `f1-sync` worktree + `sync/upstream-v0.6.15` branch (sandbox denied); push go.

## Queue, in order

1. **C141 design (operator agreed direction, P187):** webfetch allowed + audited in the v2 bench (deny answer-key sources by
   permission pattern on webfetch URL and shell command, record every fetch on the row, reference-solution overlap detector, flagged
   rows never ranked). Present the spec, get go, build (Codex worker, cold-context verifier), new scaffold id, never pooled with M59.
2. **C139(b) re-record** under the final scaffold (48K default already in `947c9cb`; C141 landed): one ≈ 20 h chain, arm
   `mem_watchdog.py`, session-tagged outputs.
3. **C140:** flag the 1.18-medium `Qwen3.8-27B-mlx-uniform-4bit` go/matrix row (answer-key webfetch) in reports. RCA artefacts:
   `$STACK_WORKDIR/m59_debug/` (pair.py, firstwrite.py, capture/, ocdb copy, codex_rca.md).
4. **C138 proposal** (probe interruption safety, in-probe memory cap replacing the watchdog).
5. Push when the operator says. Blind-judge agent canary in a new session.

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

Next decision id C142; discussion ids continue from P190.

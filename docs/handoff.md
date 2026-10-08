# Handoff — 2026-10-07 (afternoon): M59 chain IN PROGRESS (s1 pick-2 re-run, then s2); session resumed by Claude Opus 5.5 (allow-shorthand) after the Fable limit; stack UP (bench router) until the chain ends

THE one handoff. Read this, then `docs/PLAN.md` (M59 row) and `docs/open-questions.md` (C136 addendum; C137 localized; C138 OPEN).
History: `docs/lab-notebook.md` 2026-10-07 (early: build/smoke; afternoon: chain). Artefacts: `$STACK_WORKDIR/m59/` (RUNLOG.md is the
live log; `run_m59.py` runner; `chain_resume.sh` detached driver → `chain.rc`; `s1/`, `s2/` rows; `archive/s1_pick2_window558/` the
superseded pick-2 arm + original transcripts; `c137/` replay outputs; `smoke_attempt5..8/`).

## State of the world

- **Chain running** (detached `chain_resume.sh` → `run_m59.py chain s1 s2`, started 20:39Z): s1 re-runs ONLY pick 2
  (`Qwen3.8-27B-mlx-uniform-4bit`, window 630 s) on a fresh instance; then s2 (seed base 2002; pick 2 then pick 1; fresh load at the
  boundary; outputs tagged `.s2.`). ≈ 11 h from launch. The runner stops the stack at the end (`stack_stop`). Exit code in `chain.rc`.
  Monitor: `tail -F RUNLOG.md` for END / RATE CHECK / FATAL lines; per-leg RATE CHECK flags a > 5 % decode gap.
- **Memory watchdog armed** (P183, 04:05Z, `mem_watchdog.py`; exits when `after_chain.rc` appears): kills scratch processes > 8 GB RSS or orphaned from a finished item; kills are logged as `WATCHDOG KILL` in the RUNLOG. Reason: a model-written infinite loop reached 117 GB (C138 (3)).
- **s1 done for pick 1** (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, window 662 s): Python 21/22, Go 20/22. Pick-2 558 s arm archived
  (Python 19/22, Go 17/22; all misses stalls) — adaptive correction, disclose, never pool (C136 addendum).
- Stack `main` = this commit; `origin/main` = `c889661` (**not pushed**; operator: "we push later"). Fork `58eb241b` pushed, CI green.
- C137 localized: full prefill deterministic under `fused_v1` and `auto`; the cached-prefix run diverges (shrink/re-floor suspected).
  Next: the shrink-off discriminator (≈ 15 min box) AFTER the chain.
- Operator-only: delete `ts.md` and the fork `f1-sync` worktree + `sync/upstream-v0.6.15` branch (sandbox denied); push go.

## Queue, in order

1. Let the chain finish; if it stops, read `chain.rc` + RUNLOG; an INCOMPLETE leg must be archived and re-run from item one on a fresh
   instance (C138 — never resume across loaded instances).
2. Analysis: per (model, language, session) `acc_strict@budget`, convergence, nonconv kinds, window/rate/probe-hash provenance; the
   pick-2 558 s arm reported separately; descriptive scaffold delta vs the 1.18 medium rows (never pooled; Holm, TOST ±5 pp); README
   evidence tables + campaign-results entry. No pick/order change from a re-baseline.
3. C137 shrink-off discriminator; C138 proposal; push when the operator says.
4. Blind-judge agent canary (new session); candidates not queued unchanged.

## Rules learned (this session)

- Anything opencode can print into its prompt must be stable per item, never per run: scratch dir name, TMPDIR, file mtimes; the date is
  a one-day window (`prompt_date`). Diff per-request `prompt_tokens` in the worker log to locate a leak before blaming the server.
- The lean worker logs to stdout unless `MLX_VLM_LOG_FILE` is set (runserver sets it); set it in every lean start that an instrument reads.
- A draft-OFF overlay must also drop `mtp_verify_scan` (it requires `draft_kind: mtp`).
- Kill runners by process group: a killed runner left its gate child alive, which overwrote the A4 receipt of the next attempt.
- Suites must run with the stack down and without `STACK_WORKDIR` exported.
- opencode 2.0.20 sometimes emits the final `step_finish` (the capture never saw it); a mock capture is necessary, not sufficient.
- Codex workers stop and ask when a ruling is needed; answer in a follow-up prompt file, keep the `.rc` launcher.

Next decision id C138; discussion ids continue from P175.

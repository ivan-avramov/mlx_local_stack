# Handoff — 2026-10-07 (early morning): M59 BUILT and MERGED to main (opencode 2.x probe, v2 client config, A4 on v2, 1.18 frozen); smoke passed on the final code; chain awaits the operator's go; stack STOPPED

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (M59 row) and `docs/open-questions.md`
(C134–C136 RULED; C137 OPEN: residual long-generation nondeterminism). History: `docs/lab-notebook.md` 2026-10-06 (late, fork CI) and
2026-10-07 (early, M59). Artefacts: `$STACK_WORKDIR/m59/` (RUNLOG.md, `run_m59.py` runner, `make_overlay.py` + `overlay_m59_draft_off.yaml`,
`prompt_identity.py`, `items_python_go.json`, `smoke_attempt5..8/` rows + transcripts, Codex prompts/reports, review scratch dirs,
`personal_opencode.v1.backup.json`), `$STACK_WORKDIR/m59_research/` (REPORT.md, capture/FACTS.md), `$STACK_WORKDIR/ci_repro/`.

## State of the world

- **Stack is STOPPED** (runner stops it after every smoke; operator's choice to keep the daily driver down). Restart = `./runserver.sh`.
  The operator's `~/.config/opencode/opencode.json` is now the generated v2 client config (backup in `$STACK_WORKDIR/m59/`).
- Stack `main` = `09c00b8` + this handoff commit; `origin/main` = `c889661`. **NOT pushed** (operator approved the fork push only).
  Fork `../mlx-vlm` `main` = `58eb241b` = `origin/main` (pushed; `Test PRs` green on the macos-14 runner). Submodule = `58eb241b`.
- **M59 (opencode 2.x probe) is BUILT and merged** (branch `m59-opencode-v2` fast-forwarded into main; 20 commits): `benchmark/run_opencode_probe_v2.py`,
  `benchmark/bench/opencode_common.py` (shared pieces), M50 v2 tripwire in `provenance.py`, generated `benchmark/opencode_bench_v2.json` +
  `benchmark/opencode_plugins/noretry.js`, `benchmark/decode_rates.json` (C136), v2 client config `opencode_config/opencode.json`, A4-on-v2 in
  `scripts/session_pinning_gate.py` (default `--opencode v2`), the 1.18 probe FROZEN (refuses before any I/O; rows retained). Workers: Codex
  `gpt-6-astra`; verifier: Claude Opus 5.5 (allow-shorthand) cold reviews (four passes, all findings folded in).
- **Smoke (attempts 5–8, pick 1, 5 seeded-random Python items):** final attempt 8 on the final code: p1 5/5 (342 s/item), p2 4/5; A4 v2 PASS;
  scaffold prompt identity PASS; 3 of 4 comparable items byte-identical end to end. Four prompt-identity leaks were found and closed on the
  way (random scratch name, per-run TMPDIR, prepared-file mtimes, the date → `prompt_date` on rows). See the lab notebook.
- **"2× slower on 2.x" was a basis error** (cold RCA): like-for-like v2 is 0.92–1.08× of 1.18; the server decodes 15–30 % faster, the model
  writes ≈ 1.5× the tokens. Chain re-estimate ≈ 14.5 h point / 13.3 h lower bound / ≤ 22 h heavy tail.
- Suites on main with the stack down: see the last line of `$STACK_WORKDIR/m59/suite_main.rc` and the logs beside it (expected green; run
  without `STACK_WORKDIR` exported — the dsh guard test refuses an inherited one).
- Untracked: `ts.md` (operator note; `rm` was denied to the session — operator deletes it).

## Queue, in order

1. **Operator:** go for the M59 re-baseline chain (`$STACK_WORKDIR/m59/run_m59.py chain` → s1 then s2: two B picks × Python + Go, 22 items,
   seed bases 1001/2002, order-balanced, no reload leg per C135; detached with `nohup`, RUNLOG + five-minute WATCH lines; ≈ 14.5 h point).
   Also: push go for stack main; whether to buy C137 (b) (≈ 15 min replay probe).
2. After the chain: pair accuracy per session vs the 1.18 rows as a descriptive scaffold delta (never pooled); README evidence tables;
   campaign-results entry. No pick/order change from the re-baseline.
3. Blind-judge agent definition `.claude/agents/blind-judge.md` — loads only in a NEW session; canary before the next judge pass.
4. Candidates not queued: unchanged (dense prefill path; fused-kernel tuning; `auto`-path slowdown; P41; P42). M56 PARKED. ReviewBench DEFERRED.

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

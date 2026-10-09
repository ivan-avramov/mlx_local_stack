# Handoff — 2026-10-09: M61 re-record RUNNING (≈ 20 h from 01:24Z); P198 A/B + P205 panel done; C140/C143/C144 ruled

THE one handoff. Read this, then `docs/PLAN.md` (M61 row, fail-fast funnel) and `docs/open-questions.md` (C144, C143, C142,
C140, C139, C138). Results: `docs/campaign-results.md` 2026-10-09; history: `docs/lab-notebook.md` 2026-10-09. Spec:
`docs/specs/m61-web-audit-and-prompt-ab.md`. Artefacts: `$STACK_WORKDIR/m61/` (RUNLOG.md, `run_m61.py`, `run_m61_rr.py`,
`drive_ab.sh`, `drive_rr.sh`, `ab/`, `rr/`, `analysis/ab_p198.py`, `p205/`, `verify7/probe.py`).

## State of the world

- **M61 C139(b) re-record RUNNING** under `opencode-v2-web` (48K first-write allowance, webfetch allowed + audited, P202 cheat
  procedure): `drive_rr.sh` (PID 43280) → `run_m61_rr.py s1 s2`, `mem_watchdog.py` armed, stop-file `drive_rr.rc`
  (6/7/8/9 = failure). Order per session: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` then
  `Qwen3.8-27B-mlx-uniform-4bit`, Python then Go. Rows `$STACK_WORKDIR/m61/rr/<model>.rr.<s>.opencode_<lang>.jsonl`. Do not
  touch serving config or load the box until it exits. Started after main fast-forwarded to `7679bbc` and both suites passed.
- Stack `main` = this commit; `origin/main` = `c889661` (**not pushed**; operator: "we push later"). Fork `58eb241b` pushed.
- **Ruled this session:** C139(a) 48K default; C140 resolved (no accuracy regression on v2; token increase real); C141 →
  M61 audited web; C142 (repo-root URL with a query string not denied); C143 (no brevity instruction file — P205: plain v2
  code preferred 0.775 [0.525, 0.975]); C144 (new candidates agentic on v2 only; v2 gaps paid lazily — PLAN funnel).
- Operator-only: delete `ts.md`; push go (operator: after the re-record). Fork `f1-sync` worktree + local `sync/upstream-v0.6.15` removed 2026-10-09 (remote branch deleted by the operator; history: c1975b4c).

## Queue, in order

1. **Watch the re-record** to `drive_rr.rc`: per-leg `AUDIT` lines (cheat re-runs, `CHEAT REVIEW` = operator), `FLAG >5%`
   rate checks, FATAL. Then report: `bench.answer_key.report_rows` per leg (scored copies; provisional counts; cheat counts),
   acc_strict per model × language × session, head-to-head per session (two-stage cluster bootstrap), comparison to M59
   descriptive only (different scaffold — never pooled). Copy rows to `benchmark/results/<model>/opencode_v2_<lang>.m61.<s>.jsonl`
   (+ manifests, sidecars); README B evidence update; no pick/order change without operator approval.
2. (done) `m61-r5` worktree + branch removed after merge.
3. **C138 proposal** (probe interruption safety; in-probe memory cap replacing the watchdog).
4. Push when the operator says.

## Rules learned (this session)

- A token-saving prompt that keeps tests passing can still cost code quality: screen with a blind panel over test-passing
  pairs before shipping it (P205).
- The probe does not keep final solution files; rebuild from transcript `write`/`edit` replay and re-test (stubs must fail).
- Codex judge/worker calls share quota with the re-record's web auditor: run them one at a time, pause while `web_audit.py`
  runs, abort on first error.
- Codex implementers drift into docs/handoff edits and commits; forbid it in the prompt and revert on sight.
- Operator desktop activity (browser, audio, camera) cut decode ≈ 20 %; long runs need a quiet box.
- Docs-only commits during a run change the recorded `stack_head`, not the fingerprint (serving-path trees).

Next decision id C145; discussion ids continue from P209.

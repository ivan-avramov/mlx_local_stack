# Handoff — 2026-10-09 (evening): M61 re-record DONE (86/88 vs 84/88, order holds); C145/C146 OPEN; push pending operator go

THE one handoff. Read this, then `docs/PLAN.md` (fail-fast funnel, C144 agentic stage) and `docs/open-questions.md` (C146,
C145, C144, C143, C139, C138). Results: `docs/campaign-results.md` 2026-10-09; history: `docs/lab-notebook.md` 2026-10-09.
Report: `benchmark/results/m61_rr/` (`rr_report.py`, `RR_REPORT.md`). Artefacts: `$STACK_WORKDIR/m61/` (RUNLOG.md, `rr/`,
`analysis/`, `p205/`).

## State of the world

- **M61 DONE.** Re-record under `opencode-v2-web` (48K, audited web), k=2, 01:24Z → 18:55Z, rc=0, stack stopped (daily
  driver NOT started). Rows `benchmark/results/<model>/opencode_v2_<lang>.m61.<s>.jsonl` (+ manifests). 0 web fetches,
  0 cheats. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` 86/88, `Qwen3.8-27B-mlx-uniform-4bit` 84/88; README B evidence
  updated; no pick/order change proposed (all head-to-head intervals include 0; Go s2 +13.6 pp trend for the first pick).
- `main` ahead of `origin/main` (`c889661`), **not pushed** — operator said "we push after this run finishes"; needs an
  explicit in-turn go. Fork `58eb241b` pushed; fork sync worktree/branches removed.
- Ruled this session: C139(a)/(b), C140, C141 (audited web), C142, C143 (no brevity file), C144 (new candidates v2 only;
  gaps paid lazily).

## Queue, in order

1. **Push** on the operator's word.
2. **C145** (operator ruling): exclude invalid `go/counter` from opencode Go scores (regrade, recommended).
3. **C146** (operator ruling): token-counted first-write gate for future runs (recommended; spec + failing test first).
4. **C138 proposal** (probe interruption safety; in-probe memory cap replacing the watchdog).

## Rules learned (this session)

- A token-saving prompt that keeps tests passing can still cost code quality: blind panel over test-passing pairs (P205).
- The probe does not keep final solution files; rebuild from transcript `write`/`edit` replay and re-test (stubs must fail).
- Codex calls share quota with a run's web auditor: one at a time, pause while `web_audit.py` runs, abort on first error.
- Codex implementers drift into docs/handoff edits and commits; forbid it in the prompt and revert on sight.
- Operator desktop activity cut decode ≈ 20 %; long runs need a quiet box.
- Docs-only commits during a run change the recorded `stack_head`, not the fingerprint (serving-path trees).
- A short-output stall can be one open thinking stream: check `mlx_vlm.log` Stream Telemetry before attributing it.

Next decision id C147; discussion ids continue from P209.

# Handoff — 2026-10-10: M62 DONE (token/turn gate `opencode-v2-web-tg1` built, V3 7/7 + V4 3/3 live); C147 OPEN; push pending operator go

THE one handoff. Read this, then `docs/PLAN.md` (M62 row; agentic stage note) and `docs/open-questions.md` (C147, C146,
C145, C144, C138). Spec: `docs/specs/m62-token-turn-gate.md` (rev 5 + §9 build findings). Results: `docs/campaign-results.md`
2026-10-10; history: `docs/lab-notebook.md` 2026-10-10. Artefacts: `$STACK_WORKDIR/m62/` (reviews `codex_*.md`,
`fable_review4.md`, live driver `run_m62_live.py`, `RUNLOG.md`, `v3/`, `v4/`).

## State of the world

- **M62 DONE.** New scaffold `opencode-v2-web-tg1`: passive token/turn gate (T 81,920 no-progress tokens, N 40 requests,
  K 8 identical calls, ceilings 327,680 tokens / 150 requests), progress = failing-test count reaches a new minimum
  against a frozen reference universe (`benchmark/m62/universe.json`, 43 items), per-request budget-hit flag,
  bench-only `toolbounds.js` plugin, owned-process guard + memory watchdog (C138 closed). Code `c67769e`, `1c1626d`,
  `90cf34f`; suites green (3,978 passed). V2 replay 8/8 on the frozen manifest. Live 2026-10-10 07:16Z → 07:57Z: V3 7/7,
  V4 3/3 (the M61 stalls passed on short fresh paths — no information about the >41K tail; M61 stays the record).
  V5b: "cleared after fixes" → **C147** before any tg1 chain. Stack stopped; daily driver NOT started.
- The legacy `opencode-v2-web` path is unchanged (M61 reproducible). No pick/order/README change.
- `main` is ahead of `origin/main` (`c889661`), **not pushed** — needs the operator's explicit in-turn go.
- P221 (operator sign-off on strict new-minimum progress, claude-fable-5-1 review F12) still unanswered; built as specified (strict).

## Queue, in order

1. **Push** on the operator's word.
2. **P221** sign-off (strict new-minimum progress vs the looser Phase H rule).
3. **C147** before the first tg1 chain: live injected positives (test-only lowered thresholds, ≈ 30 min), a tg1 chain
   runner (no fixed 6 h kill; exact-item validation; incomplete-leg archive/restart), `/tmp` escape diagnostic.
4. **P223** at the first C144 candidate: tg1 (re-record both picks under tg1) vs the frozen `opencode-v2-web` path.

## Rules learned (this session)

- Read the pinned client's source for every accounting field: opencode's `tokens.input` excludes cache reads and
  `tokens.output` excludes reasoning; live tool events and the export order parallel calls differently.
- A config endpoint can answer before plugins activate; prove plugin load from a call that awaits activation.
- Capture a real failure from the real toolchain before trusting a parser's mock (go1.21 `[build failed]` is plain stdout).
- A pre-registered fixture can be wrong: when the instrument disagrees, verify independently and correct it openly.
- A process guard may kill only processes it registered or inherited through verified (pid, create_time) ancestry.
- A model can write outside its TMPDIR (`/tmp`); contain or record, never blanket-sweep.
- Cold reviews in series keep finding real defects; stop when findings turn to details, then validate live.

Next decision id C148; discussion ids continue from P224.

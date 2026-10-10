# Handoff — 2026-10-10: M62 DONE (token/turn gate `opencode-v2-web-tg1` built, V3 7/7 + V4 3/3 live); C147 OPEN (deferred); P221/P222/P223 ruled; pushed

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
- `main` pushed 2026-10-10 on the operator's word; forks `../mlx-vlm` / `../mlx-serve` already at origin, submodules pinned to their HEADs.
- Rulings 2026-10-10 (operator): P221 strict new-minimum progress approved; P222 C147 deferred until a tg1 chain is queued;
  P223 new C144 candidates run under tg1, both picks re-recorded under tg1 first.

- **P229 workdir cleanup (2026-10-10):** 151 GB of model weights deleted (each sha-matched to its public `caslca/*`
  Hugging Face copy). Chain drivers committed to `benchmark/chains/` (`8246c91`). Orphan branch `evidence` (`1ec50d6`,
  ~107 MB, 5,511 files) holds the irreproducible raw artifacts (transcripts, C82/C84 outputs, overlays, reports),
  PII-scrubbed with `SCRUB_MANIFEST.json`, credential scan clean, replay of all 454 manifest entries identical.
  Fresh-machine runbook: `benchmark/README.md`. Pending: push `main` + `evidence` (operator word), then delete the
  rest of `$STACK_WORKDIR` (~40 GB). opencode 2.0.20 exists only via Homebrew/source (not npm) — `brew pin opencode`.

## Queue, in order

0. Push `main` + `evidence`, verify fresh-clone restore, then delete the workdir remainder (P229).
1. Nothing else queued. **C148** (flaky process monitor) with C147. When a tg1 chain or the first C144 candidate is queued: **C147** first — live injected positives
   (test-only lowered thresholds, ≈ 30 min; needs an approved small build), a tg1 chain runner (no fixed 6 h kill;
   exact-item validation; incomplete-leg archive/restart), `/tmp` escape diagnostic.
2. Then re-record both picks under tg1 (P223, ≈ 20 h k=2 chains), then candidates under tg1.

## Rules learned (this session)

- Read the pinned client's source for every accounting field: opencode's `tokens.input` excludes cache reads and
  `tokens.output` excludes reasoning; live tool events and the export order parallel calls differently.
- A config endpoint can answer before plugins activate; prove plugin load from a call that awaits activation.
- Capture a real failure from the real toolchain before trusting a parser's mock (go1.21 `[build failed]` is plain stdout).
- A pre-registered fixture can be wrong: when the instrument disagrees, verify independently and correct it openly.
- A process guard may kill only processes it registered or inherited through verified (pid, create_time) ancestry.
- A model can write outside its TMPDIR (`/tmp`); contain or record, never blanket-sweep.
- Cold reviews in series keep finding real defects; stop when findings turn to details, then validate live.

Next decision id C149; discussion ids continue from P230.

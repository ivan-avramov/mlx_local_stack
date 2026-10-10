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
  Hugging Face copy). Chain drivers in `benchmark/chains/`. Orphan branch `evidence` (`1f62c13`, ~5,300 files) holds
  the irreproducible raw artifacts, PII-scrubbed (`SCRUB_MANIFEST.json`), credential scan clean, no text from the
  operator's private instruction files; opencode 1.18.30 transcripts EXCLUDED (that scaffold loaded the operator's
  global instructions). Replay of the M62 manifest on the branch passes. Runbook: `benchmark/README.md` "Fresh machine".
- **P230:** the v2 probe's opencode 2.0.20 is bench-owned (`scripts/install_bench_opencode.sh` →
  `$STACK_WORKDIR/opencode-2.0.20`, byte-identical to the recorded executable); brew/daily opencode untouched.
- **C148 DONE** (`d94947b`): monitor survives macOS AccessDenied on exiting processes; 20/20 clean.

## Queue, in order

0. DONE 2026-10-10: `main` + `evidence` pushed; fresh GitHub clone + `git archive` restore replays the M62
   manifest (all criteria pass). Workdir cleaned (40 GB): only `opencode-2.0.20/` and `private-118/` remain.
   `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit-mtp-drafter` published (public, probe-only). **P232 open:** the
   opencode 1.18.30 transcripts (193 files, 2.1 MB, contain paraphrases of the operator's private global
   instructions) exist only in `$STACK_WORKDIR/private-118/` — private off-laptop copy or let go; never public.
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

Next decision id C149; discussion ids continue from P233.

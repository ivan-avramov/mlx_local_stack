# Handoff — 2026-10-10: next work is C147 (clear the tg1 scaffold for k=2 chains), then the P223 re-record

THE one handoff. Read this, then `docs/open-questions.md` C147 (full owed list), `docs/specs/m62-token-turn-gate.md`
(rev 5 + §9 build findings), `docs/PLAN.md` (M62 row; agentic-stage note) and `benchmark/chains/README.md`.

## State of the world

- **M62 DONE.** Scaffold `opencode-v2-web-tg1`: passive token/turn gate (T 81,920 no-progress tokens, N 40 requests,
  K 8 identical calls, ceilings 327,680 tokens / 150 requests); progress = failing-test count reaches a new minimum
  (strict, P221) against `benchmark/m62/universe.json` (43 items); per-request budget-hit flag; bench-only
  `toolbounds.js`; owned-process guard + memory watchdog. Live V3 7/7, V4 3/3; V2 replay passes. Code
  `benchmark/bench/{token_turn_gate,structured_grade,proc_guard,tg1_runner}.py`, `benchmark/m62/`.
- **C148 DONE** (`d94947b`): monitor treats macOS `AccessDenied` on an exiting process as transient; 20/20 clean.
- **P230:** v2 probe opencode 2.0.20 is bench-owned: `scripts/install_bench_opencode.sh` → `$STACK_WORKDIR/opencode-2.0.20`
  (byte-identical to the recorded executable `da6c61cd…`). Never use or change the brew/daily opencode.
- **Workdir was emptied 2026-10-10 (P229).** Only `opencode-2.0.20/` remains. Before any run, rebuild inputs per
  `benchmark/README.md` "Fresh machine" (corpus at `7e0611e`, NLTK data). Raw evidence (M59/M61/M62 transcripts,
  M62 reviews/RUNLOG, overlays) is on branch `evidence`: `git archive origin/evidence | tar -x -C "$STACK_WORKDIR"`.
  opencode 1.18.30 transcripts are in the PRIVATE repo `mlx_local_stack-private` only — never publish.
- Chain drivers for M54–M62 are frozen in `benchmark/chains/` (M59 runner reused by M61/M62; `m62/run_codex.sh` runs
  Codex; it writes under `$STACK_WORKDIR/m62` — create the dir first).
- No pick/order/README change. Stack stopped; daily driver NOT started. `main` and `evidence` pushed.

## Queue, in order (C147 is deferred until a tg1 chain is queued — P222; start it when the operator says so)

1. **C147 (1) live injected positives.** Test-only lowered-threshold policy mode, labelled, rows never pooled. On the
   box: one memory-allocation kill, one no-progress stop, one K (identical-call) stop. Proves the live path
   stop → owned-descendant kill → worker cancellation → export reconciliation. ≈ 30 min box time. New code → spec,
   operator approval, cold review, implement, verify.
2. **C147 (2) tg1 chain runner** replacing the reused M59 runner (fixed 6 h `subprocess.run` kill bypasses cleanup;
   "complete" = row count). Needs: deliberate timeout/cancellation through `tg1_runner`, exact-item + manifest
   validation, incomplete-leg archival and fresh-instance restart, leg timeouts from pilot means + heavy-tail
   allowance, 5-minute watcher (AGENTS.md), k=2 instances with distinct paired schedules + same-seed reload control.
   Start from `benchmark/chains/m59/run_m59.py` and `benchmark/chains/m62/run_m62_live.py`; put it in the repo.
3. **C147 (3) `/tmp` escape diagnostic.** Record `/tmp` paths written by the model (from transcripts/events) per item;
   clean exactly those files; never sweep `/tmp`.
4. **C147 (4) optional:** retain hashed structured-grader reports so intermediate failing counts are auditable.
5. **P223:** re-record both picks (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `Qwen3.8-27B-mlx-uniform-4bit`)
   under tg1, k=2 chains (≈ 20 h), then C144 candidates under tg1. Never pool tg1 with the M61 `opencode-v2-web` rows.

## Rules learned (2026-10-10)

- `pgrep -f <pattern>` matches its own wait loop; wait on a PID or an output file.
- macOS psutil raises `AccessDenied`, not `NoSuchProcess`, for an own-uid process mid-exit.
- Export a pytest shell WITHOUT `STACK_WORKDIR` (`env -u STACK_WORKDIR`); the test guard expects it unset.
- Before publishing raw transcripts: scrub home paths/username/hostname, search for literal credential values, and
  shingle-match the operator's private instruction files (`~/.claude/CLAUDE.md`, memory, `~/.codex/AGENTS.md`).
- Publish only what cannot be reproduced; verify every deletion by sha against its published copy first.

Next decision id C149; discussion ids continue from P233.

# Handoff — 2026-10-06 (late night): night done — merge gate IDENTICAL and adopted locally; M60 run (Math500 inconclusive at the edge, judge no drift); stack STOPPED; fork + stack NOT pushed

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (M60 row: run; M59 row: research +
capture done) and `docs/open-questions.md` (C133 OPEN: M60 outcome; C130 adopted locally, push pending; C132 CI fixes on the branch;
C129 (2) answered; C119/C128 done). Day narrative: `docs/campaign-results.md` 2026-10-06 (night, two entries), `docs/lab-notebook.md`
2026-10-06 (late / night). Artefacts: `$STACK_WORKDIR/m60/` (runner, summary, packets, judge stage dirs, verdict tools),
`$STACK_WORKDIR/upstream/2026-10-06/` (merge worktree on `sync/upstream-v0.7.6`, gate runner + run, G0, reviews, ASSESSMENT.md),
`$STACK_WORKDIR/m59_research/` (opencode v2 source clone, REPORT.md, `capture/FACTS.md` + 22 runs), `$STACK_WORKDIR/c119/`, `c125/`, `c128/`.

## State of the world

- **Stack is STOPPED** (router, OpenWebUI, compose down; the operator's opencode v2 background service was stopped for the night too).
  Restart = `./runserver.sh`; opencode v2 restarts its service on first use.
- Stack `main` = this commit, **ahead of `origin/main` (`4edf1d3`) by 8 commits, NOT pushed**: `4080a43` seed-base, `40197b5` probe pin,
  `f7172d5` docs, `946290e` red tests, `23f3147` transport abort, `4233247` docs, `9582d75` docs, + this (M60 rows, judge_m60, submodule
  bump to `b17b12a9`, docs).
- **Fork `../mlx-vlm` `main` = `b17b12a9`** (fast-forwarded to `sync/upstream-v0.7.6` after the IDENTICAL gate), **NOT pushed**;
  `origin/main` is still `664c2ead`. The stack submodule `src/mlx-vlm` points at `b17b12a9` — a clone of the stack cannot resolve it until
  the fork is pushed. `uv.lock` unchanged (`requirements.txt` identical to before). mlx-serve unchanged (`3f2c87c`).
- Fork CI (`ivan-avramov/mlx-vlm`): turns green only after the fork push (style commit + parity workflow on the synced ref are on `main`
  now); `Upload Python Package` and `PR contributor reminder` workflows are disabled in the repo settings (reversible).
- Tests: `benchmark/bench/tests` 3264 passed / 0 failed (default `TMPDIR`); fork suite 5828 passed / 0 failed; 8 parity audits pass.

## What the night established

- **Merge identity gate:** fork `664c2ead` vs `b17b12a9` (upstream v0.7.6 merged): 23 seeded requests × old / new / new-after-reload →
  0 differing fields; 196K retrieval prompt 5/5 on the new source, no compaction (upstream's chat compaction is opt-in, default off).
- **M60 on the merged source:** Math500 `acc_strict` 0.98 vs 0.99 (`m40on`), −1 pp CI95 [−5, +2] → INCONCLUSIVE (lower bound on the
  edge; 3 discordant items incl. the C63 universal miss); vs OFF reference +1 pp; judge panel (3 judges, gate PASS 6/6, 420 verdicts):
  shipped state preferred 0.425 [0.31, 0.54], p = 0.19 → no detectable drift at n=40. 100/100 + 40/40 converged; pilot-twice identical.
  By the pre-registered rule the PROVISIONAL labels on native16 / M57 / M58 STAY; no registry, pick or order change. **C133 asks the
  operator: accept (recommended) / buy Math500 power (≈ 2.6 h OFAT bundle on 100 new ids) / rule PASS-at-the-edge.**
- **opencode 2.x is a workable hermetic scaffold** (`m59_research/capture/FACTS.md`): `body` overlay carries sampling + seed to the wire;
  per-run isolation needs `--standalone` + redirected HOME/XDG + `OPENCODE_CONFIG_DIR` + `OPENCODE_DISABLE_PROJECT_CONFIG=1` +
  `-opencode.config.compatibility`; a one-line local `retry` plugin gives retries = 0; the fork ignores `max_completion_tokens` (send
  `max_tokens`); v2 never loads CLAUDE.md; session pinning works via `x-session-id`.

## Queue, in order

1. **Rulings owed:** C133 (M60 outcome); **push** of fork `main` (`b17b12a9`) then stack `main` (8 commits) — explicit go needed; both
   together, fork first.
2. **M59 spec** (opencode 2.x probe) from the capture facts: v2 probe with the C124 transport classification (exit 1 + JSON `error` event;
   two consecutive `step_start` = a retried request → abort ungraded), `noretry.js` in the bench config dir and in the provenance hash,
   M50 policy change for `OPENCODE_CONFIG_DIR` + `OPENCODE_CONFIG_CONTENT` (accepted in principle, C131), v2-native client config through
   configgen (disable the vllm poller, `agents.title`, compaction choice), freeze the 1.18 probe once the v2 smoke passes. Spec returns
   for approval (M54 funnel), then `--limit 5` smoke and the first seeded chain.
3. **Blind-judge agent definition** `.claude/agents/blind-judge.md` (`omitClaudeMd: true`) is committed but loads only in a NEW session —
   try it before the next judge pass; fallback = Explore agents (read-only; verdicts as text + `extract_verdicts.py`).
4. Candidates not queued: unchanged (dense prefill path; fused-kernel tuning; `auto`-path slowdown; P41; P42). M56 PARKED. ReviewBench DEFERRED.

## Rules learned (this night)

- Monitor pipelines: `grep --line-buffered` only — a trailing `sed`/`cut` swallowed 30 minutes of gate events (second time; memory note exists).
- The Explore agent type is the blind judge that works today; it may be read-only, so judges must be able to return verdicts as text.
- Headless `claude --bare -p` is "Not logged in" from the session shell; a mid-session project agent definition is not loadable.
- `uv run --frozen --no-sync` for every router start on an unadopted submodule sha (metadata drift would otherwise re-sync the venv).
- A judge leg that is sequential and slow (Codex ~1 call/min) should start FIRST, before any GPU phase, next time.

Next decision id C134; discussion ids continue from P147.

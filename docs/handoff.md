# Handoff — 2026-10-06 (night): re-evaluation done — M60 approved and built (not run); opencode 1.18 wrapped; opencode 2.x researched; upstream merge assessed; suite green; stack UP, no bench run

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (M60 row: approved, built, not run; M59
row: research done) and `docs/open-questions.md` (C130 plan awaiting approval; C119 awaiting a ruling; C127/C128/C129 ruled or done).
Day narrative: `docs/lab-notebook.md` 2026-10-06 (late) and (night). Artefacts: `$STACK_WORKDIR/m60/` (runner, tests, `JUDGE.md`,
dry-run output), `$STACK_WORKDIR/m59_research/` (`REPORT.md`, opencode v2.0.20 source clone), `$STACK_WORKDIR/upstream/2026-10-06/`
(`ASSESSMENT.md`), `$STACK_WORKDIR/c125/` and `c128/` (review and worker prompts, outputs, `run_codex_review.sh`, `run_codex_work.sh`).

## State of the world

- Stack `main` = `946290e` + this docs commit, **ahead of `origin/main` (`4edf1d3`), NOT pushed**: `4080a43` (AgentBench `--seed-base`),
  `40197b5` (session-cache probe + gate pinned to the bench opencode), `f7172d5` (docs), `946290e` (red tests repaired), this commit.
- Forks unchanged: mlx-vlm `main` 664c2ead (33 commits behind upstream, tags v0.7.4–v0.7.6 fetched), mlx-serve `main` 3f2c87c.
- `benchmark/bench/tests`: **3199 passed, 3 skipped, 0 failed.** Fork suite on `main`: 5477 passed (run by the assessment, 61 s).
- Daily driver UP under M58. The only model traffic this session: one run of `scripts/session_pinning_gate.py` (OpenWebUI leg
  skipped) — PASS. No bench router started; nothing measured.
- The operator's opencode v2 background service (`opencode serve --service`, started 2026-10-05) is running; see M60 note below.

## Operator rulings this session (2026-10-06)

- C127: M60 design approved as P116–P125 (pilot as phase A; no shipped-state predictor-OFF arm; lift PROVISIONAL labels on PASS).
- Direction: no further work on opencode 1.18 — wrap to a stable state, then move to opencode 2.x. C124 folded into M59.
- C129 (1): the bench-owned `--version` preflight directory is ratified. C128: fix the red tests if relevant to 2.x (done).
- Asked: consider merging upstream `mlx-vlm` before new work (C130, assessed; plan below awaits approval); parallelise through
  subagents, with Codex `gpt-6-astra` as worker as well as reviewer.

## Recommended sequence (awaiting the operator's confirmation)

1. **Upstream merge build, CPU, now** (C130): fix the parity-audit baseline first; branch `sync/upstream-v0.7.6`; merge the v0.7.6 TAG;
   compaction opt-in (failing test first); `_strip_assistant_thinking` moved into the normalization helper; lazy `cryptography`;
   C104 test reconciliation; full fork suite; prompt-render identity gate on recorded requests (CPU); cold review.
2. **M59 step 1, CPU, in parallel:** mock-endpoint capture of the eight items listed in `m59_research/REPORT.md` (body overlay on the
   wire, system prompt contents, side requests, polling, `--standalone` cleanliness, error paths and the 10× retry, export, `PWD`).
   Needs a ruling on the M50 policy for v2 (`OPENCODE_CONFIG_DIR` + `OPENCODE_CONFIG_CONTENT` are refused by today's tripwire).
3. **One stack-down night:** identity gate for the merge (same seeded requests on the old and the new source, plus one ~200K prompt
   showing no compaction) → if byte-identical, M60 on the merged state; if not, revert the submodule, run M60 on `664c2ead`, hold the
   merge for attribution. Then the judge pass (no GPU; judges without instruction files, canary first).
4. **M59 build** from the capture facts: v2 probe with the transport classification built in, v2-native client config through
   configgen, then `--limit 5` smoke and the first seeded chain; freeze the 1.18 probe once the v2 smoke passes.
5. **C119** (`generate` transport abort) — small, opencode-independent; awaiting a go.
6. Candidates not queued: unchanged (dense prefill path; fused-kernel tuning; the 1.4–3.6 % `auto`-path slowdown; P41; P42). M56 PARKED
   (C110). ReviewBench DEFERRED (C122).

## Before the M60 night

- `run_m60.py --dry-run` must exit 0 with only the expected would-refuse lines; `test_run_m60.py` must pass.
- Decide whether the operator's opencode v2 service must be stopped for the night: by source it polls `127.0.0.1:8000` every 30 s
  unless its vllm plugin is disabled (unverified on this box; the router logs do not record GETs).
- The real-run path of the runner (router start, generation, monitor loop) is unexercised; the first minutes of the night are its test.

## Rules learned (this session, both halves)

- After merging two reviewed branches, run the full suite on the MERGED tree.
- A refusal test asserts the SPECIFIC refusal text, never only an exit code plus a generic word.
- Any opencode spawn, including `--version`, runs under a bench-owned environment (1.18.30 creates its directories first).
- Only an ABSENT seed base means legacy base 0; a present null hashes to a different schedule.
- opencode 2.x: per-run environment exists only under `--standalone`; `debug config` reports the shared service, not the run; set
  `PWD` as well as `cwd`; model `options` are not sampling — use `body`.
- Subagent judges are not blind to the repo's instruction files unless the agent definition says so.
- Codex: launch detached with an exit-code marker (`run_codex_review.sh` / `run_codex_work.sh`); its sandbox cannot bind sockets, so
  mock-server tests must be verified outside it.
- A subagent of the research type cannot write report files; extract its report from the task transcript instead.

Next decision id C131; discussion ids continue from P146.

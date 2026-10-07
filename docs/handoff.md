# Handoff — 2026-10-06 (late, second session): fork CI diagnosed and fixed (push pending); M59 opencode 2.x spec written (C134, awaiting approval); stack STOPPED by operator choice

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (M59 row: spec written) and
`docs/open-questions.md` (C134 OPEN: the M59 design's judgement calls + two housekeeping asks; C133/C130/C119 done). History:
`docs/lab-notebook.md` 2026-10-06 (late) "fork CI" entry. Artefacts: `$STACK_WORKDIR/ci_repro/` (Python 3.10 + MLX 0.32.3 repro venv,
logs), `$STACK_WORKDIR/m59_research/` (REPORT.md, `capture/FACTS.md` + 22 runs, `capture/tools/{mock,run}.py`), `$STACK_WORKDIR/m60/`,
`$STACK_WORKDIR/upstream/2026-10-06/`.

## State of the world

- **Stack is STOPPED** (operator's choice; stays down unless they say otherwise). Restart = `./runserver.sh`. No opencode service running.
- Stack `main` = `f0ae091` (two commits past `origin/main` `c889661`): `b61221a` submodule bump + lab notebook, `f0ae091` M59 spec +
  C134 + PLAN row. **NOT pushed.**
- Fork `../mlx-vlm` `main` = `58eb241b` (one commit past `origin/main` `b17b12a9`, branch `ci/macos-runner-test-fixes` merged ff).
  **NOT pushed.** Stack submodule `src/mlx-vlm` = `58eb241b`.
- Fork CI on `b17b12a9`: `Upstream parity` green; `Test PRs` run 37558071759 **13 failed / 5807 passed** (macos-14 runner, MLX 0.32.3,
  Python 3.10). All 13 pass on the box under the same pair → runner-specific; fixed in `58eb241b` (test/CI only). The CI rerun is the
  red→green for the prefill-profile fix (mechanism inferred, see the notebook) and happens on push.
- Tests: fork suite on `58eb241b` (fork venv, Py 3.12 / MLX 0.32.2) 5829 passed / 0 failed; `benchmark/bench/tests` unchanged since
  3264 passed.
- Worktrees pruned: stack `.claude/worktrees/agent-*` (both merged; branches deleted), fork `upstream/2026-09-13` (merged; branch deleted).
  Left for the operator (C134): fork `f1-sync` (`sync/upstream-v0.6.15`, 3 commits never merged, superseded), stack `m54/wt-*`
  (detached, clean, contained in main), fork `upstream/2026-10-06` (merge worktree, clean).
- Untracked in the stack: `benchmark/results/judge_m60/.../gate.json` (naming hook; regenerable with `bench.judge_gate`) — commit with
  a bypass is the operator's call; `ts.md` is an operator note (a talk transcript), not touched.

## Queue, in order

1. **Operator:** push go for fork `58eb241b` + stack `f0ae091`? (CI reruns on push.) Rule on C134 (M59 design judgement calls (1)–(5),
   gate.json bypass, f1-sync).
2. **M59 build** after approval (`docs/specs/m59-opencode-v2-probe.md`): Codex `gpt-6-astra` (probe v2 + provenance + tests) and
   Sonnet (configgen v2 emitters + goldens + READMEs + 1.18 freeze) from self-contained prompts with known positives; Claude + Codex
   cold reviews (Codex detached with an `.rc` marker); full suite on the merged tree; then the `--limit 5` smoke twice on the lean
   router (`MLX_VLM_CACHE_SESSION_MAX=1`, draft-OFF overlay, M50/C106, daemon) ≈ 45 min box; A4-on-v2; then the re-baseline chain
   (P161, ≈ 15 h lower bound / 18–20 h budget) only on the operator's go.
3. Blind-judge agent definition `.claude/agents/blind-judge.md` — loads only in a NEW session; canary before the next judge pass.
4. Candidates not queued: unchanged (dense prefill path; fused-kernel tuning; `auto`-path slowdown; P41; P42). M56 PARKED. ReviewBench DEFERRED.

## Rules learned (this session)

- An exported `TMPDIR` that does not exist breaks MLX's Metal JIT (`temp_directory_path … Not a directory`) and fails ~50 tests that
  look unrelated; create the dir first.
- zsh: `kill $(pgrep …)` with a multi-line result is one "illegal pid" string — loop over the pids.
- macos-14 CI is ~4× slower than the box and releases Metal buffers late: absolute peak-memory thresholds are not portable; measure
  deltas from a quiesced reset.
- The box's `opencode` is the brew 2.0.20 symlink; the probe's 1.18.30 pin lives under `$STACK_WORKDIR/opencode-1.18.30/`. v2 facts of
  record are in `capture/FACTS.md`, not the (stale v1) opencode docs.

Next decision id C135; discussion ids continue from P162.

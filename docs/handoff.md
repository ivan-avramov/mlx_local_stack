# Handoff — 2026-10-06 (late): queue items 1–3 worked — M60 design awaits approval (C127); C125 follow-ups built and committed (not pushed); transport-abort proposal awaits approval; stack UP, no GPU work done

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/PLAN.md` (M60 row: design awaiting approval; M59
queued) and `docs/open-questions.md` (C127, C128, C129 OPEN; C119/C124 proposal written). Day narrative: `docs/lab-notebook.md`
2026-10-06 (late), `docs/campaign-results.md` 2026-10-06 (two entries, unchanged today). Artefacts: `$STACK_WORKDIR/c125/` (review
prompts, Codex + Claude reviews, `run_codex_review.sh`), `$STACK_WORKDIR/opencode-probe/version-env/` (new fixed preflight directory).

## State of the world

- Stack `main` = `40197b5` + this docs commit, **2 code commits ahead of `origin/main` (`4edf1d3`), NOT pushed**. Forks unchanged:
  mlx-vlm `main` 664c2ead, mlx-serve `main` 3f2c87c; submodules match.
- Daily driver UP under M58 since 18:00 UTC; this session sent it no request and ran no model. No bench router was started.
- Test baseline (`benchmark/bench/tests`, default `TMPDIR`): **20 failed, 3176 passed, 3 skipped** — the 20 predate this session (C128: C121
  tests use a model absent from the registry; the M58 manifest guard refuses). Every file touched today is green.
- Bench opencode: pinned 1.18.30 at `$STACK_WORKDIR/opencode-1.18.30/`; `session_cache_probe` leg B and
  `scripts/session_pinning_gate.py` now use it too (never PATH). The gate script was changed but NOT run (needs the live router).
- `ts.md` is the operator's untracked note. Two stale agent worktrees under `.claude/worktrees/agent-*` can still be removed.

## What this session did

1. **Queue item 1 — M60 design (C127, awaiting approval; nothing built or run).** Certification of the final shipped state of
   `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on Math500 and the judge panel. PLAN row M60 carries the arm, criteria and cost.
   Scope correction: the M40 Math500/judge rows predate native16 too (TQ4 KV, fork `420c01e1`), so one arm covers four provisional
   serving changes and cannot attribute a failure (bisect pre-registered as an escalation). Open sub-rulings: no shipped-state
   predictor-OFF arm; the seeded pilot is phase A of the night, not run before approval (stack is up as the daily driver).
2. **Queue item 2 — C125 follow-ups, built, reviewed, committed.** `4080a43`: required `--seed-base` for `run_agentbench_os.py`
   (resume identity; compare gate checks manifests and rows; the M54 chain 3/4 arms still pass it). `40197b5`: `session_cache_probe`
   leg B + the session-pinning gate pinned to the bench opencode, `--pure` on the discovery call, version preflight under a bench-owned
   environment. One cold review each (Claude + Codex `gpt-6-astra`); all findings folded in.
3. **Queue item 3 — transport-abort proposal written** (`docs/proposal-transport-abort.md`, P126–P132; C119 + C124). Fail-closed
   allowlist: only the probe-timeout DNF keeps an error row in `generate`; the opencode probe grades only a clean completed session or
   a gate kill with a verified-alive router. Step 1 of the build measures opencode 1.18.30's failure signatures on the mock endpoint.
   No regrade or rerun asked (the gaps are latent in the committed corpus).

## Queue, in order

1. **M60** — on approval of C127: write `docs/specs/m60-shipped-state-certification.md` (terse), build the self-contained phase script
   under `$STACK_WORKDIR/m60/` with a dry-run, then run when the operator says the stack is down. Judge pass afterwards (no GPU).
2. **C128** — repair the 20 red tests (fixture resolves the scan for the fake model + one golden test on the real registry); needs a go.
3. **Transport abort** — on approval of the proposal: P129 measurement first, then `generate`, then the probe; TDD + cold reviews.
4. **C129** — rulings: ratify the version-env preflight write; isolate leg B's environment (recommended) or record/freeze.
5. **M59 — opencode v2 scaffold migration** (PLAN row). Add to its scope: the session-pinning gate's A4 leg covers only v1 today.
6. **First seeded opencode chain** when a B question needs it; `run_agentbench_os.py` chains now need `--seed-base` per session (two
   bases, the reload control reuses its session's base).
7. **Candidates not queued:** unchanged from the previous handoff (dense prefill path; fused-kernel tuning; the 1.4–3.6 % `auto`-path
   slowdown; P41 watch-list; P42). M56 PARKED (C110). ReviewBench DEFERRED (C122).

## Rules learned (this session)

- After merging two reviewed branches, run the full suite on the MERGED tree; "green on each branch" produced 20 red tests on `main`.
- A refusal test asserts the SPECIFIC refusal text; exit code plus a generic word let a test keep passing after its target check became
  unreachable.
- `opencode --version` is not read-only: 1.18.30 creates its config/data/state/tmp directories first. Any opencode spawn, including
  `--version`, runs under a bench-owned environment.
- Only an ABSENT seed base means legacy base 0; a present null hashes to a different schedule and must refuse.
- Codex reviews: launch detached with an exit-code marker file (`$STACK_WORKDIR/c125/run_codex_review.sh`); a tool-bound background
  command is capped at 10 minutes. Do not put a reviewer's `TMPDIR` under `$STACK_WORKDIR` when it runs `test_run_agentbench_os.py`
  (four fixture-dependent failures).

Next decision id C130; discussion ids continue from P138.

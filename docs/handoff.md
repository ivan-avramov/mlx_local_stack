# Handoff — 2026-11-17 (session 26, in progress: Wave 2 tg1 RUNNING; tg2 blocked on S26-P6 / P11 / P12; C360 guard in a stash)

THE one handoff. Read this, then `docs/PLAN.md` rows M76, M83, then `docs/open-questions.md` top entries (newest first: C359, S26-P1 …
S26-P7, then C358 …). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: guardrails prevent wrong data or
wasted time, not ceremony; GPU time is the binding resource; run-time operational calls are the designer's (C353); all work on this box (C350).
C359's "proceed on recs, stop only for major blockers" is SESSION 26 ONLY — a later session asks again. Label points `S26-P<n>`.

Decisions: session 26 ruled C359, C360, C361 (next **C362**); discussion ids so far S26-P1 … S26-P13.

## Goal

Certify `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on TQ4 KV + `tq4_attention: m72_exact` + MTP ON as the shipped default (−13 GB at
256K). Ship when stage 1 memory ✔, stage 2 exactness ✔, stage 3: A1 ✔ (look 1 PASS), A5 ✔ (look 1 PASS), A7, A8 decider all PASS, no tg2
HOLD, no panel / interaction flag; else per-axis signals → the operator. M1 dropped from stage 3 (C352).

## FIRST

1. `main` is ahead of `origin/main` (`3fc079ca`) by session-26 docs and the S26-P8 fix (`ad1c5533`). Not pushed (no push asked).
2. Running: Wave 2 tg1 sequencer (`$STACK_WORKDIR/m76/p426/wave2/sequencer.pid`; v8 `611520b5…`; 10 legs: pilot pair → gate → amendment →
   s1, s2, s3 → reload) and its Cellar guard (`wave2/guard.log`; PAUSE on any Homebrew change). Power 140 W / 28 V; `pgrep -fl "claude -p"`.
3. Four-eyes STRICT run "S26 agent env" (C360 + C361), spec `docs/specs/s26-agent-env.md` v1.1 (design review r1 Sol + GLM applied,
   ledger `docs/reviews/s26-agent-env/`). Baseline `7a535a28`. Implementer = fresh Claude Opus 5.5 `claude -p` in
   `worktrees/fe-s26-impl` (output `m76/s26-impl-1.json`); test-writer = Claude Sonnet 5.5 `claude -p` (resumable) in `worktrees/fe-s26-tw`,
   tests in `benchmark/bench/tests/s26_frozen/` (output `m76/s26-tw-1.json`). Phase A (write only, `py_compile` only, BUSY strings
   forbidden) runs beside Wave 2; phase B (resume both: test-writer runs on baseline → freeze → reveal → candidate run; implementer runs
   its tests) in the GPU gap after Wave 2; then change review (Sol + GLM `verify`), fix round if needed, then **Accept = an explicit
   operator ask with the final diff, findings and test results (NOT covered by C359 / "keep going", which covered Go only)**; then merge, stack gate on the new `main`, tg2 arms rebuilt, `python -m bench.tg2_gradle_home prefill`, tg2 positives. Old draft worktree
   `worktrees/s26-p9-guard` = starting code only (remove at merge). Review checkout `worktrees/s26-review` (remove at merge).
   **While Wave 2 runs, `main` takes docs commits only** (each harvest re-imports `bench` from `main`'s working tree; `git add` by path);
   helpers and my own commands never carry a BUSY marker string (`chain_ops.BUSY`) in argv.

## State

- S26-P1: stage-3a Wave 1 readout from `main` = the acceptance run byte for byte (`$STACK_WORKDIR/m76/s26-readout/`): A1 PASS (+2.0 pp,
  loss bound 0.0), A5 PASS (0 / 72 discordant, loss bound 9.2 pp = the n-72 exact bound), 0 flags; decode X / N16 0.85–0.92.
- tg2 (B4b-1 acceptance criterion 3): positives on `m76-g-n16` sealed **FAIL** (`m76/p426/tg2/attempt1-FAIL/`). Grades 8 / 8 and stall 4 / 4
  work; loop 1 / 4, alloc 0 / 4 (the model declines the planted instructions: S26-P6). The agent self-provisions toolchains over the network
  (rustup into the per-run hermetic HOME; `brew install openjdk@17` onto the shared host — reverted; S26-P5). **Both OPEN for the operator; no tg2
  leg runs until ruled.**
- Wave 2 tg1 (A7): arms `m76-w2-{n16,x}` at the gated `3c199587` (S26-P7); rehearsal manifest `01ba1be9…`; rehearsal `20261117a` launched
  2026-11-17 22:13Z (R1 n16 / x, R2 mismatch on x → INVALID expected, R3 kill on n16; ≈ 4.5 h).
- Panel: runs once after Wave 2, from the B8 that includes A7 (S26-P4).
- Box toolchains (C360 (3), installed 2026-11-17 16:3x): `rust` 1.100, `openjdk@21` (force-linked; host had no JDK), `cmake` 4.5 (+ deps
  libgit2, z3, llvm (keg-only, unlinked), pkgconf, giflib, webp, libtiff, little-cms2). The real `~/.gradle` the positives created is archived
  (`archive/s26-dot-gradle-20261117/`; S26-P12).
- tg2 waits on the operator: S26-P6 (inject positives harness-side), S26-P11 (per-item fetch caches), S26-P12 (JVM ignores the hermetic HOME).

## Next, in order

1. Rehearsal result → `p426_freeze v8 --lever kv --corpus tg1 --pair n16,x --arm-worktree … --rehearsal-manifest … --r1-off/--r1-on (R1 roots)
   --r2 --r3 --build-inputs $STACK_WORKDIR/m76/p426/wave2/build_inputs.json --historical-walls benchmark/results/p426/wave2/historical_walls.json
   --out m76/p426/wave2/run/v8_base.json` → `p426_wave2 run --lever kv --pair n16,x … --out-base m76/p426/wave2 --record-dir m76/p426/wave2/run`
   (pilot → gate → amendment → s1 → re-check → s2 → s3 per the look rule → reload). Guard beside it (`host_guard.sh <pid> <out-base>/PAUSE <log>`).
2. On the operator's S26-P5 / S26-P6 ruling: the tg2 environment / inject spec change (four-eyes strict), then positives again
   (`m76/p426/tg2/`, build inputs there; run record dir `m76/p426/tg2/run`), rehearsal `m76/p426/rehearsal.tg2/`, v8, pilot pair, sizing report.
3. After Wave 2: B8 + signals with A7, then the panel (S26-P4), then the stage-3a readout.
4. B4b-2 spec + design review (no pytest) beside GPU legs; small fail-closed fixes (S25-P10, PII username pattern) in a GPU gap.

## Worktrees and scratch

- Wave 2 tg1 arms `$STACK_WORKDIR/worktrees/m76-w2-{n16,x}` (branches `m76-w2-n16` = `3c199587`, `m76-w2-x` = `0fc05281`): Wave 2, keep until its
  harvest. tg2 arms `m76-g-{n16,x}` (`c7c6993a` / `de87df98`): stage 3b, keep. Stage-3a Wave 1 arms `m76-q-{n16,x}` (their 255 untracked rows each
  are byte-identical to `main`'s); stage 1–4 arms `m76-f45-*`: keep until stage 4 harvest.
- Every new arm: `uv sync --frozen`; `.venv-bench` from `benchmark/requirements-bench.lock`; `src/mlx-vlm/.venv` by `p475_kv._ensure_fork_venv`'s
  recipe (editable fork, constraints from the arm `.venv` freeze; a plain `uv sync` there gives other pins). Check `uv pip freeze` sha equal to the s3 arms'.
- Scratch publish clones: `m76/p426/tg2/main-clone`, `m76/p426/rehearsal/main-clone-20261117a` (P576 workaround).

## Rules learned (session 26)

- Helpers beside live legs (side-agent note, adopted): anything that runs tests waits for a GPU gap; a read-only panel review may
  overlap a leg only when launched after that leg's start census and finished before the next leg is due (`chain_core` census:
  any foreign argv carrying a `chain_ops.BUSY` marker aborts the leg). Briefs go on stdin, never in argv.
- An inject positive that asks the model to misbehave measures the model's compliance, not the harness; this model declines harmful asks.
- An agentic leg can mutate the host (package managers write outside any redirected HOME): snapshot the Homebrew Cellar around every leg.
- A panel frozen against a B8 record is bound to that record's sha: freeze once, from the final B8.
- v8 needs a PASS gate receipt for exactly the reference arm's commit: pick arm commits that have one.
- `brew uninstall` autoremoves orphaned formulae: pass `HOMEBREW_NO_AUTOREMOVE=1`, or reinstall what it took.

## Rules learned (session 25)

- A four-eyes implementer runs named test files only, full output to files, 2 h limit; the full suite runs once, as the designer's gate (C356 (3)).
- Allowlist the exact command forms a helper must run. Read a generator's write contract before a long run.
- A test timeout is a margin over a measured duration. "checked" names the check and its result; otherwise "expected".
- Root-cause a counter mismatch across rungs before naming a mechanism. Launch the stack gate from a `main` checkout (S25-P10).
- Sweep new docs for the username before committing. A history rewrite renames every later commit: commit the map.

## Rules learned (sessions 18–24, condensed; full text in git history of this file)

- Waiters match names the code emits. Run the real path early: mocks hide real-path facts. Refusals never echo matched PII.
- Specs fix behaviour + named seams with a deviation rule (C348). The PII / naming hooks read docs, tests and commit messages too.
- `bench.*` modules run from `benchmark/`. `pytest` (or `mlx-serve` in an argv) refuses P369 / qualify runs; GPU stages and helpers cannot overlap.
- A pre-registered decision rule needs its error simulated. Measure memory per process, real graph shape, known positives.
- After a reboot start OrbStack before any gate; docker lives in `~/.orbstack/bin`. Read a FAIL receipt's `failure_artifacts` before rerunning.
- Fork changes to upstream-shared files need a `# Fork` marker; run `bench.modelnames` over a fork diff before committing.

## Archives (local, no push)

- `$STACK_WORKDIR/archive/tg2-universe-ff76573b/` (session 25), `m72/superseded-instrument-v{1,2}/`, `archive/p475-base-*`,
  `archive/session18-worktrees/`; branches `archive/*` (M72 1.3 cited by `benchmark/results/m72/m72-13/README.md`).

# Handoff — 2026-11-17 (session 25 → 26: B4b-1, B8 readout, tg2 grader fix built + reviewed + integrated; universe re-frozen; history scrubbed; gate re-run)

THE one handoff. Read this, then `docs/PLAN.md` rows M76, M83, then `docs/open-questions.md` top entries (newest first: S25-P10 … S25-P1,
C357, C356, then C355 …). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: guardrails prevent wrong data or
wasted time, not ceremony; GPU time is the binding resource; run-time operational calls are the designer's (C353); all work on this box (C350).
C356's "proceed on recs, stop only for major calls" was SESSION 25 ONLY — ask again. Label points `S26-P<n>`.

Decisions: session 25 ruled C356–C357 (next **C358**); discussion ids restart at `S26-P1`.

## Goal

Certify `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on TQ4 KV + `tq4_attention: m72_exact` + MTP ON as the shipped default (−13 GB at
256K). Ship when stage 1 memory ✔, stage 2 exactness ✔, stage 3: A1, A5 (incl. per-task gates), A7, A8 decider all PASS (point ≥ −5 pp, loss
bound ≤ 10 pp), no tg2 HOLD, no panel / interaction flag; else per-axis signals → the operator. M1 dropped from stage 3 (C352).

## FIRST

1. Stack gate run 2 on `c7c6993a` (tip of `m76-s25-integration`), launched from a `main` checkout (S25-P10): result in
   `$STACK_WORKDIR/gate/s25-c7c6993a-run2.log` + the receipt beside it. Run 1 FAILed only on the S25-P10 branch-name test (14,899 passed).
2. If PASS: the operator's Accept (one table: B4b-1, tg2 grader, B8, universe re-freeze; the open row **V3** — B4b-1's `inject_verify` now also
   accepts tg1 rows that record a hash-verified `datefreeze`; designer rec keep). Then S25-P8: fast-forward `main` to `c7c6993a` (+ docs above it)
   and push `main` at the gated sha (push only on the operator's explicit word in that turn). Fork / mlx-serve unchanged.
3. Box: nothing running besides the gate; power 140 W / 28 V at session end.

## State

- `m76-s25-integration` (local; history scrubbed, C357) = `4bcd9af9` B4b-1 (C351; spec v5 + v5a; ledger `docs/reviews/m76-b4b1/`, rounds 1–3)
  → `c8087c84` merge of `main` → `93c2cb8a` tg2 grader fix (C355 (1); spec v1 + v1a, v1b; ledger `docs/reviews/m65-tg2-timeout/`, rounds
  1–2) → `f588c617` B8 readout (C354, C355 (2)(3), C356 (1); spec v1.1 + v1.1a; ledger `docs/reviews/m76-b8-kinds/`, rounds 1–2) →
  `09e23732` tg2 universe re-frozen + draw re-derived + pins (S25-P6 diff: same items / statuses / leaves / permutations) → docs (`c7c6993a`).
  Old → new shas: `docs/reviews/s25-history-scrub-map.md`.
- B8 real-data acceptance (`docs/reviews/m76-b8-kinds/designer-acceptance-report.md`): 10 / 10 planned Wave 1 pairs, 0 flags; negatives behave.
  `m76/ids.json` regenerated (S25-P1: the counter now renders `reasoning_effort: medium`; 131,072 = 130,776 served; 196,608 budgets as served).
- tg2: grader `m65-tg2-v3`; universe `2bf6add4`, draw `82875e1d`; old ones archived `$STACK_WORKDIR/archive/tg2-universe-ff76573b/`.
- `main` local = `fc0174c0` (docs only above `origin/main` `3c199587`).

## Next, in order (after the push)

1. Stage-3a readout: B8 + signals over the real Wave 1 with the merged code (the acceptance run used the four-eyes copy; re-run from `main`,
   `$STACK_WORKDIR/m76/s24-p7-check/run.sh` pattern) → the A1 / A5 / panel steps of stage 3a's readout.
2. B4b-1 real-output acceptance (criterion 3; ledger L17): positives on the box, R2 on X / R3 on N16, pilot pair, sizing report vs both budgets
   (S24-P9). GPU.
3. GPU: stage-3a Wave 2 (A7 tg1; build `s3`; arms `m76-q-n16` `1b3dd025` / `m76-q-x` `d4c44a9d`) and stage 3b (A8). B4b-2 spec + design review
   during the decider (`docs/specs/m76-b4b2-a8-consumers.md`; carry L9: every new tg2 consumer passes `grader="tg2"`; L16 `row_scores.py`).
4. Small fail-closed fixes (failing test, fix, one cold read): S25-P10 (the tg1-file guard: the gate records + exports the pushed base;
   today it errors off `main` and passes vacuously from a `main` containing the build); the PII hook learns the username pattern from the
   machine config (C357). Until S25-P10 lands, gate from a `main` checkout that does NOT yet contain the build.

## Worktrees and scratch

- Stage-3a arms `$STACK_WORKDIR/worktrees/m76-q-{n16,x}`; stage 1–4 arms `m76-f45-{n16,x,v,xo}` (keep until stage 4 harvest).
- Four-eyes runs (inputs to the merged work; harvested into `docs/reviews/`): `fe-m76b4b1`, `fe-m76b8k`, `fe-m65grade` — remove after the push;
  older `fe-*` regenerable, ask before deleting. Freeze cache `$STACK_WORKDIR/m65/freeze-s25/`. B8 acceptance outputs `m76/s25-b8-accept/`.
- Local branches: `m76-b4b1-tg2-runner` (superseded by the integration branch; delete after the push), `m76-s25-integration` (merge → delete).

## Rules learned (session 25)

- A four-eyes implementer runs named test files only (red tests + files importing changed modules), full output to files, 2 h limit; the
  full suite runs once, as the designer's gate (C356 (3)). Link `.venv-bench` into every copy; exclude it (and designer-copied docs) from
  candidate diffs.
- Allowlist the exact command forms a helper must run (relative and absolute interpreter paths) — a missing form cost a fix round.
- Read a generator's write contract before a long run (the freezer refuses to overwrite: 75 min, rescued by its cache).
- A test timeout is a margin over a measured duration, never the measured minimum (S25-P5).
- "checked" in a record names the check and its result; otherwise write "expected" (S25-P6).
- Root-cause a counter mismatch across rungs before naming a mechanism: a constant offset and a proportional one have different fixes
  (S25-P1: the deployed `reasoning_effort` changed the calibration, not a template overhead).
- Launch the stack gate from a `main` checkout (S25-P10).
- Sweep new docs for the username before committing; the hook misses it (C357).
- A history rewrite renames every later commit: commit the old → new map and update designer records forward (S25-P9).

## Rules learned (session 24)

- A waiter matches names the code emits — derive them from the planner or count log events; never retype a leg name (S24-P20).
- Run the real path early: mocked tests hid B8's `m1` KeyError, rule 2d's cross-arm comparisons, the A5 frozen-count offset and the
  N16 M1 gate — one real run found all four (S24-P19, P21, P23, P24).
- A refusal message never echoes matched PII: the sequencer log that carries it is published (S24-P18).
- Recording real tool outputs as fixtures surfaces defects (the tg2 timeout misclassification, S24-P22).
- A spec that dictates code-level detail converges slowly; fix behaviour + named seams with a deviation rule (C348).
- The PII / naming hooks also read your own docs, tests and commit messages: split literal paths / hostnames, use full model names.
- `bench.*` modules run from `benchmark/` (the gate too).

## Rules learned (sessions 18–23, condensed; full text in git history of this file)

- A test helper running a real thread beside a fake fast clock needs explicit ordering at every handoff; tests must not read local-only
  branches (commit sha-pinned fixture copies).
- `pytest` (or `mlx-serve` in an argv) on the box refuses P369 / qualify runs; GPU stages and four-eyes helpers cannot overlap; timed legs
  run on a quiet box; gate power strictly before any GPU launch.
- A pre-registered decision rule needs its error simulated; prefer exact bounds with few discordant items; a conditional Clopper–Pearson on
  the discordant split is not a safe loss bound.
- Mocked tests miss real-path facts; ask the panel to trace real call chains; make the fake reproduce the real-box fact first.
- Push the gated sha itself when docs sit above it; the pre-push hook needs the machine config sourced.
- Measure memory per process (OS footprint ledger + MLX allocator), real graph shape, known positives; never memfree.
- After a reboot start OrbStack before any gate; read a FAIL receipt's `failure_artifacts` before rerunning.
- Fork changes to upstream-shared files need a `# Fork` marker; run `bench.modelnames` over a fork diff before committing.

## Archives (local, no push)

- `$STACK_WORKDIR/archive/tg2-universe-ff76573b/` (session 25), `m72/superseded-instrument-v{1,2}/`, `archive/p475-base-*`,
  `archive/session18-worktrees/`; branches `archive/*` (M72 1.3 cited by `benchmark/results/m72/m72-13/README.md`).

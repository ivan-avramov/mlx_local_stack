# Handoff — 2026-11-03 (session 15: rehearsal `20261102a` PASS, Wave 2b harvested, OFF gate FAIL → P607 fixed, arms re-cut; gates → push (C270) → Wave 2c launch)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P608, P607, C270, P604, P603, P602, P601, P595–P600, C269,
P594, C268, …), specs `docs/specs/p586-relaunch-build.md` v1.1, `docs/specs/p603-export-capture.md` (P603 as BUILT differs: the export
goes to the stored transcript file, no item-record field) and `docs/specs/p426-b2-tg1-wave2.md` §1, §4.3, §4.5, §5.1, §10, §11, §12, §16.8.
Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: "i trust you - keep going towards certifying MTP
for the picks"; updates every 15–20 min; ask only at Accept / pushes / scope changes; lead calls filed in open-questions as they land.

## FIRST — verify (each "no" is a blocker)

1. Is the Wave 2c sequencer running (`bench.p426_wave2 run`, out-base `$STACK_WORKDIR/p426/wave2c`, ≈ 17 h)? Running → watch, start
   nothing alongside; exited → `wave2c/sequence.log`, each leg's `leg.json`, `pairs/*.json`. Not launched → do "Next" 1–3 first.
2. `main` ahead of `origin/main` only by what C270's push did not carry; `evidence` = `e18cad07` (pushed if C270 completed);
   `git status` clean.
3. Arms: `p426-off` `4adb596a`, `p426-on` `46ca41b9` (tree == `main` `e805f3e8`; re-cut for P607, OFF diff byte-identical to
   `63415dcb`'s; identities unchanged: probe `da76b4cb…`, policy `f56705f9…`, generation `d59bb9ed…`); worktrees clean.

## Next, in order

1. **Gates** (quiet box, sequential, read each verdict, never chain — P541): `bench.local_gate run --repo stack --sha 4adb596a…`
   (the new OFF arm), then the same on `main`'s tip (this handoff's docs commit). The `63415dcb` gate FAILED (P607). Each ≈ 55 min; output `$STACK_WORKDIR/scratch/gate-<sha8>.txt`.
2. **Build inputs**: `$STACK_WORKDIR/p426/wave2b/build_inputs.json` with `stack_suite_receipt` / `_sha256` = the `4adb596a` receipt →
   `$STACK_WORKDIR/p426/wave2c/build_inputs.json`.
3. **Freeze + run**: `p426_freeze v8 --off-worktree … --on-worktree … --out $STACK_WORKDIR/p426/wave2c/records/v8_base.json
   --rehearsal-manifest $STACK_WORKDIR/p426/rehearsal/manifest-20261102a.json --r1-off/--r1-on/--r2/--r3 <20261102a leg roots>
   --build-inputs … --historical-walls benchmark/results/p426/wave2/historical_walls.json`; then `p426_wave2 run --worktree-off/--worktree-on
   … --out-base $STACK_WORKDIR/p426/wave2c --record-dir $STACK_WORKDIR/p426/wave2c/records --main-root <checkout> --historical-walls …`
   (`nohup`, from the checkout root, `PYTHONPATH=benchmark`). A leg stop: diagnose; same-code rerun = `--rerun <leg> --rerun-reason …`
   (frozen seeds repeat item behaviour — rerun only a random cause).
4. **Push (C270, approved for this push only)** after a PASS on `main`'s tip: `git push origin <gated sha>:main` (never a later tip),
   `evidence`, `archive/p426-wave2.v8-af0711cf-off`, `archive/p426-wave2.v8-4104c7fc-off`, and `p426-off` (`4adb596a`) as `archive/p426-wave2-off`.
   ON archives held (P606 (a)); the rehearsal arms `archive/p426-rehearsal.20261102a-{off,on}` held (P608). A FAIL: push nothing, report.
5. After Wave 2c: B8 pair verification / B6 signals per spec §12 (client-cut endings per arm + the C269 sensitivity), README evidence, the
   MTP certification call (per-axis signals to the operator). Quiet windows: gates on the ON arms `2a173f8b`, `7a0817d3`, `8516cf23` and
   their archive push (P606, operator approval); **P602 = build P383 per plan v4** (four-eyes); C258 crossover (P577 (a)); P503 fixes
   (C261); P576; the opencode 2.2.5 re-pin (C269 B′).

## State — 2026-11-02

- **Rehearsal `20261102a`** (arms `63415dcb` / `8516cf23`, 18:29–22:59Z): R1 off / on VALID (4/5 each; `go/crypto-square` fails both:
  OFF `client_inactivity` at 3662 s, ON `stalled` + client kill), dossier `r1__off-a1__on-a1` PASS; R2 INVALID `reconciliation mismatch
  (injected)` on `go/beer-song`, chain rc 2 = the P602 ambient-orphan refusal (`orphans_unattributed` not empty; known residual); R3 VALID,
  `python/beer-song` = `kill_inflight_failed`, `go/crypto-square` = `kill_client_aborted`. As expected throughout.
- **Wave 2b harvested** as superseded: `main` `f16b0112` (529 files, `wave2.v8-4104c7fc/`, run records + both dossiers), `evidence`
  `e18cad07` (3584 files, 38 MB; scanned clean). Untracked copies moved to `$STACK_WORKDIR/scratch/superseded-wave2b-untracked/` (byte-identical
  apart from HARVEST.json paths / `created` / self-hash). The arm worktrees hold no `.env`.
- **P603 + P604** built in `1eaf8fd6` (grader `m62-structured-v3`, probe `da76b4cb…`, policy `f56705f9…`; never pooled with Wave 2b).
- **C270**: push before Wave 2c (approved); P606 (a) — ON archives wait for exact-sha gates.
- **P607** (lead call): the `63415dcb` gate FAILED 13 / 9967 — P604's grader bump never registered with the P371 / C147 identity pins
  (no behaviour defect). Fixed `347cf8d0` + review r1 `e805f3e8` (`docs/reviews/p607/`); arms re-cut; `20261102a` stays valid (the freeze
  never compares rehearsal commits). Follow-up: `benchmark/m65/pilot_universe.json` embeds v2 (stale; rebuild before any M65 use).

## Worktrees / scratch (each with its resolution)

- `stack-p426-off`, `stack-p426-on` (`p426-off` / `p426-on`): the Wave 2c arms — remove after Wave 2c's harvest and the archive pushes.
  `archive/p426-wave2.v8-*-{off,on}`: superseded arms — OFF pushed with C270, ON after their gates (P606).
  `archive/p426-rehearsal.20261102a-{off,on}` (`63415dcb` / `8516cf23`): the rehearsal's arms, cited by the Wave 2c v8 — P608.
- `stack-c258x-off` (`c258x-off`): keep for P577; remove after.
- `$STACK_WORKDIR/p426/wave2/` (first v8) and `p426/wave2b/` (both harvested): delete after an inventory table.
- `$STACK_WORKDIR/scratch/superseded-wave2-untracked-20261101/`, `superseded-wave2b-untracked/`, `evstage-20261101-wave2v8` (committed
  `58411357`), `evstage-20261102-wave2v8b` (committed `e18cad07`), `p586-4eyes/`, `p602-review/` (the shelved minimal patch),
  `p603-p604-review/`, `p604-universe/`, `harvest-v8b-*.txt`: delete after the push / inventory. `scratch/p594-opencode-2.2.5/`: keep for the re-pin.
- `$STACK_WORKDIR/p426/rehearsal/{20261030,…,20261102a}` + manifests + `main-clone-*`: `20261102a` is frozen into the Wave 2c v8; the rest
  delete after the inventory. `$STACK_WORKDIR/c258x/` (scrub the charger serial before any harvest).

## Rules learned (session 15)

- A push needs a PASS receipt on the exact pushed sha: gate the tip before a long run, push the gated sha (`<sha>:main`) so later docs
  commits do not invalidate it.
- An ON arm (one commit on its OFF arm) needs its own receipt; a tree identical to an ungated `main` commit is no help (P606).
- A version / identity bump runs the FULL gate before its arms are cut (P607: the targeted suites missed 13 pins).
- A harvest re-run re-stamps HARVEST.json (`created`, self-hash) besides the namespace paths: compare the rest byte for byte.

## Rules learned (session 14, carried)

- A guard's "fails safe" claim must hold for the largest gap the mechanism allows (DST hides exactly 3600 s; sol r2 P1).
- A default argument binds at import (`run=subprocess.run` defeated the test fakes; the "stall").
- Never put backticks in an unquoted heredoc that builds a brief (the shell runs them); a re-cut runs under `set -e`, never `;`-chained.
- File names can look like addresses (`compile@go1.27.3-…count`); a main-bound index must not list private names (P599).
- Dry-run the harvest over every real tree before relaunch (found P599).
- With frozen seeds, item behaviour repeats across attempts (`go/crypto-square` ran away identically 5 times): a rerun cures only a
  random cause (P603's pipe race), never a model-driven one (P604).
- A piped capture of a client that exits can lose its tail at the pipe buffer: capture large outputs to files (P603).
- A grader's "infrastructure" class must be attributable: protected inputs (tests, go.mod) failing = infra; the model's own files failing
  = a scored fail (P604 review).
- A planned fix may never have been built: check the code, not the ruling (C180 / P383 → P602).

Next decision id C271; discussion ids continue from P609.

# Handoff — 2026-11-02 (session 14 END: Wave 2b superseded by P603/P604; arms re-cut for Wave 2c; rehearsal `20261102a` RUNNING; nothing pushed)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P604, P603, P602, P601, P595–P600, C269, P594,
C268, …), specs `docs/specs/p586-relaunch-build.md` v1.1, `docs/specs/p603-export-capture.md` (P603 as BUILT differs: see below) and
`docs/specs/p426-b2-tg1-wave2.md` §1, §4.3, §4.5, §5.1, §10, §11, §16.8. Model names: FULL registry names only. Review rounds: 3 per
artifact. Operator stance this session: "i trust you - keep going towards certifying MTP for the picks"; updates every 15–20 min; ask
only at Accept / pushes / scope changes; lead calls are filed in open-questions as they land.

## FIRST — verify (each "no" is a blocker)

1. The rehearsal sequencer (`bench.p426_wave2 rehearsal`, out-base `$STACK_WORKDIR/p426/rehearsal/20261102a`, manifest
   `manifest-20261102a.json` `f0de0982…`, launched 2026-11-02 18:29Z, ≈ 4.5 h): running → wait, start nothing alongside; exited → read
   `20261102a/sequence.log`, each leg's `leg.json`, `pairs/r1__*.json`.
2. `main` = `1eaf8fd6` + this handoff's docs commit, ahead of `origin/main`; `evidence` two local commits ahead (`c42bca0c`,
   `58411357`); `git status` clean apart from the untracked Wave 2b harvest copies under `benchmark/results/p426/wave2/` (step 2).
3. Arms: `p426-off` `63415dcb` (OFF diff byte-identical to the first v8's), `p426-on` `8516cf23` (tree == `main` `1eaf8fd6`),
   `restore_diff_problems` = []. Local archive branches: `archive/p426-wave2.v8-af0711cf-{off,on}`, `archive/p426-wave2.v8-4104c7fc-{off,on}`.

## Next, in order

1. **Rehearsal verdicts** (expected, as `20261101b` gave on the previous arms): R1 off / on VALID with `1 + 2` Python then 2 Go items +
   dossier PASS; R2 INVALID `reconciliation mismatch (injected)` on `go/beer-song` (its chain exit may be the P602 ambient-orphan refusal —
   the leg record still reads INVALID with the injected reason; that is the known residual); R3 VALID with `python/beer-song` =
   `kill_inflight_failed` (and `go/crypto-square` may be `kill_client_aborted` or a budget stall). `go/crypto-square` runs ≈ 60 min on
   OFF, ≈ 35 on ON. Anything else: diagnose from the records (export + worker telemetry), propose, red-first.
2. **Harvest the superseded Wave 2b** (v8 `4104c7fc…`, out-base `$STACK_WORKDIR/p426/wave2b`) into `benchmark/results/p426/wave2.v8-4104c7fc/`
   exactly as session 14 did for the first v8 (`0b185867` / evidence `58411357`): for each attempt `tg1-p426-{off,on}-pilot.a1`,
   `tg1-p426-off-s1.a1`, `tg1-p426-on-s1.a1` (INVALID, P603), `tg1-p426-on-s1.a2`, `tg1-p426-on-s2.a1` (INVALID, P604):
   `python -m bench.p426_harvest wave2 --leg-root … --main-root <checkout> --evidence-stage $STACK_WORKDIR/scratch/evstage-<date>-wave2v8b
   --operator-email "$(git config user.email)" --worktree $STACK_WORKDIR/worktrees/stack-p426-{off,on} --namespace wave2.v8-4104c7fc`
   (the worktree's `logs/mlx_vlm.log` still holds the byte ranges — the re-cut did not touch `logs/`); the run records (`records/v8_base.json`,
   `records/amendment.json`, `sequence.json`) via `p426_harvest.publish_run_files(…, namespace=…)` and the dossiers
   (`pairs/pilot__off-a1__on-a1.json`, `pairs/s1__off-a1__on-a2.json`) via `publish_dossier(…, namespace=…)` (a `Scrub` built like
   `p426_wave2.BoxSeqOps._scrub`); dry-run first (`--dry-run`); then move the untracked `benchmark/results/p426/wave2/*` copies to
   `$STACK_WORKDIR/scratch/superseded-wave2b-untracked/` after checking every file is byte-identical in the namespace (HARVEST.json differs by
   paths only); commit `data(bench)`; the evidence stage to the `evidence` branch through a temporary worktree (as `58411357`). Never paired.
3. **The gate on the new OFF commit `63415dcb`** (`bench.local_gate run --repo stack --sha <full sha>`, ≈ 55 min, quiet box), then build
   inputs = `$STACK_WORKDIR/p426/wave2b/build_inputs.json` with the new receipt sha → `$STACK_WORKDIR/p426/wave2c/build_inputs.json`.
4. **Freeze + run** (the operator's Go is the standing "keep going" unless they say otherwise): `p426_freeze v8 --out
   $STACK_WORKDIR/p426/wave2c/records/v8_base.json --rehearsal-manifest …-20261102a.json --r1-off/--r1-on/--r2/--r3 <20261102a roots>
   --build-inputs … --historical-walls benchmark/results/p426/wave2/historical_walls.json`; then `p426_wave2 run --worktree-off/--worktree-on
   … --out-base $STACK_WORKDIR/p426/wave2c --record-dir $STACK_WORKDIR/p426/wave2c/records --main-root <checkout> --historical-walls …`
   (`nohup`, from the checkout root, `PYTHONPATH=benchmark`); legs 1–8 ≈ 17 h. A leg stop: diagnose; a same-code rerun is
   `--rerun <leg> --rerun-reason …` (deterministic item behaviour repeats with the frozen seeds — rerun only for a random cause).
5. After Wave 2c: B8 pair verification / B6 signals per spec §12 (client-cut endings per arm + the C269 sensitivity), README evidence, the
   MTP certification call (per-axis signals to the operator). Then quiet windows: **P602 = build P383 per plan v4** (four-eyes), the gate
   on `main`'s tip for the push, C258 crossover (P577 (a)), P503 fixes (C261), P576, the opencode 2.2.5 re-pin (C269 B′).

## State — 2026-11-02

- **Wave 2b** (v8 `4104c7fc…`, arms `67375468` / `7a0817d3`, superseded): pilots VALID + dossier PASS; `off-s1.a1` VALID (`go/crypto-square`
  = `kill_client_aborted` live); `on-s1.a1` INVALID (P603: export capture cut at 65,536 bytes); `on-s1.a2` VALID, dossier
  `s1__off-a1__on-a2` PASS (descriptive: 42/43 each arm, the only fail `go/crypto-square` both arms); `on-s2.a1` INVALID (P604).
- **P603 + P604 built** (`1eaf8fd6`, sol r1 2 major adopted + r2 1 minor adopted, `docs/reviews/p603-p604/`): the export goes to the stored
  transcript file with one re-export (no extra files, no row-schema change — NOT the spec's item-record field); the Go grader scores a
  load error located in a non-test `.go` file / the mixed-package form in exactly `/work` / an import cycle (rc 1, no events); grader
  `m62-structured-v3`; `m62/universe.json` rebuilt (43 items identical apart from `grader_version`, sha `63bae993…`). Suites 2548 passed,
  5 skipped; all 349 stored Go grades parse. Probe `da76b4cb…`, policy `f56705f9…` (new identity: never pooled with Wave 2b).
- **Rehearsal `20261101b`** (previous arms): all as expected, incl. R3 `go/crypto-square` = `kill_client_aborted` live. Gate PASS on
  `67375468` (receipt `df5eba89…`).
- **P602** (lead call): C180's ambient-orphan rule never built; residual for Wave 2c; build P383 after.
- Earlier this session: P586–P593 (`92a6fe68`), P601 (`2b25f86b`), C269, the first v8 harvested (`0b185867` / `58411357`).

## Worktrees / scratch (each with its resolution)

- `stack-p426-off`, `stack-p426-on` (`p426-off` / `p426-on`): the Wave 2c arms — archive as `archive/p426-wave2-{off,on}` at the push
  (P567), then remove. `archive/p426-wave2.v8-*-{off,on}`: superseded arms — push with the archives.
- `stack-c258x-off` (`c258x-off`): keep for P577; remove after.
- `$STACK_WORKDIR/p426/wave2/` (first v8) and `p426/wave2b/` (after step 2): harvested — delete after an inventory table.
- `$STACK_WORKDIR/scratch/superseded-wave2-untracked-20261101/`, `scratch/evstage-20261101-wave2v8` (committed `58411357`),
  `scratch/p586-4eyes/`, `scratch/p602-review/` (the shelved minimal patch), `scratch/p603-p604-review/`, `scratch/p604-universe/`
  (the rebuild, installed): delete after the push / inventory. `scratch/p594-opencode-2.2.5/`: keep for the re-pin.
- `$STACK_WORKDIR/p426/rehearsal/{20261030,…,20261101b}` + manifests + `main-clone-*`: earlier attempts; `20261102a` + `main-clone-20261102a`:
  current. `$STACK_WORKDIR/c258x/` (scrub the charger serial before any harvest).

## Push (one, at the end of a session, operator approval)

`main` (level full: a PASS gate on its tip — run after Wave 2c), `evidence` (`c42bca0c`, `58411357` + the Wave 2b / 2c stages), the arm
archive branches. Read every gate verdict before the push; never chain them (P541).

## Rules learned (session 14)

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

Next decision id C270; discussion ids continue from P605.

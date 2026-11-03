# Handoff — 2026-11-03 (session 15: Wave 2c COMPLETE — 8 legs VALID, 4 dossiers PASS, harvested d23d019d / b6ec7819; next: B6 / B8 (P613))

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P616, P615, C274, C273, C272, P613, P611, P610, P609, C271, P608, P607, C270, P604, P603, P602, P601, P595–P600, C269,
P594, C268, …), specs `docs/specs/p586-relaunch-build.md` v1.1, `docs/specs/p603-export-capture.md` (P603 as BUILT differs: the export
goes to the stored transcript file, no item-record field) and `docs/specs/p426-b2-tg1-wave2.md` §1, §4.3, §4.5, §5.1, §10, §11, §12, §16.8.
Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: "i trust you - keep going towards certifying MTP
for the picks"; updates every 15–20 min; ask only at Accept / pushes / scope changes; lead calls filed in open-questions as they land.

## FIRST — verify (each "no" is a blocker)

1. Nothing running: no `p426_wave2` / `opencode run` / `mlx-serve` processes, :8000 free.
2. `main` = `origin/main` `62bc46df` + docs commits (`6c7595a5`, `46ef163b`, `840d5b63`, this handoff) + `d23d019d` (Wave 2c data);
   `evidence` = `origin/evidence` `e18cad07` + `b6ec7819` (Wave 2c evidence). Push needs operator approval: docs-only commits first
   (`git push origin <last docs sha>:main`), then the data commit (each push's introduced commits must be all-docs or all-data, P541).
3. Arms `p426-off` `4adb596a` (pushed as `archive/p426-wave2-off`), `p426-on` `46ca41b9` (ON archive waits, P606 (a)).

## Next, in order

1. **P613:** step 1 DONE (`369831ed` code + 241 tests, four-eyes accepted; provisional A7 sheet `5dd19e23`
   `benchmark/results/p426/SIGNALS.md`). Next: the gate on `main`'s tip → push (approval); step 2 = the Wave 1 adapters (A1, M1, A2, A3, A4)
   + the rule-6 cross-wave check (four-eyes, same spec v2); step 3 = the panel run (B3 extended: `build="s2"`, A7 packets); step 4
   = the final sheet → the MTP certification
   call (per-axis signals to the operator; C269 client-cut sensitivity; P611 noise noted).
2. Push (operator approval): the docs commits, then `d23d019d`, then `evidence`.
3. Quiet windows: P606 ON-arm gates (`2a173f8b` PASS, `7a0817d3` PASS, `46ca41b9`) → their archive push (C272); the Wave 1 ON head
   `f2b61127` (local branch `archive/p426-wave1-s2-on`) needs its own gate + push approval; **P602 = build P383 per plan v4**; C258 crossover (P577 (a)); P503 fixes (C261); P576; opencode
   2.2.5 re-pin (C269 B′); M65 pilot universe rebuild under v3.

## State — 2026-11-02

- **Rehearsal `20261102a`** (arms `63415dcb` / `8516cf23`, 18:29–22:59Z): R1 off / on VALID (4/5 each; `go/crypto-square` fails both:
  OFF `client_inactivity` at 3662 s, ON `stalled` + client kill), dossier `r1__off-a1__on-a1` PASS; R2 INVALID `reconciliation mismatch
  (injected)` on `go/beer-song`, chain rc 2 = the P602 ambient-orphan refusal (`orphans_unattributed` not empty; known residual); R3 VALID,
  `python/beer-song` = `kill_inflight_failed`, `go/crypto-square` = `kill_client_aborted`. As expected throughout.
- **Wave 2b harvested** as superseded: `main` `f16b0112` (529 files, `wave2.v8-4104c7fc/`, run records + both dossiers), `evidence`
  `e18cad07` (3584 files, 38 MB; scanned clean). Untracked copies moved to `$STACK_WORKDIR/scratch/superseded-wave2b-untracked/` (byte-identical
  apart from HARVEST.json paths / `created` / self-hash). The arm worktrees hold no `.env`.
- **P603 + P604** built in `1eaf8fd6` (grader `m62-structured-v3`, probe `da76b4cb…`, policy `f56705f9…`; never pooled with Wave 2b).
- **C270 done** 2026-11-03 ≈ 01:58Z: gates PASS on `4adb596a` (9972 passed, receipt `bf536df1…`) and `main` `62bc46df` (9987 passed);
  pushed `main` `eed0da39..62bc46df` (full), `evidence` `05161ba0..e18cad07` (data-only), `archive/p426-wave2.v8-af0711cf-off`,
  `archive/p426-wave2.v8-4104c7fc-off`, `archive/p426-wave2-off` (`4adb596a`). ON archives wait (P606 (a)).
- **Wave 2c** (v8 `353ff506…`, 2026-11-03 01:58–17:31Z): all 8 legs VALID, dossiers pilot / s1 / s2 / reload PASS; harvested `main`
  `d23d019d`, `evidence` `b6ec7819` (re-verified, scanned clean). Descriptive: OFF 83/86, ON 84/86; item wall 455 vs 293 min.
- **P610 → P611**: cross-attempt divergence is input-side (tool-visible mtimes), equal on both arms; reloads reproduce pilots exactly.
- **P607** (lead call): the `63415dcb` gate FAILED 13 / 9967 — P604's grader bump never registered with the P371 / C147 identity pins
  (no behaviour defect). Fixed `347cf8d0` + review r1 `e805f3e8` (`docs/reviews/p607/`); arms re-cut; `20261102a` stays valid (the freeze
  never compares rehearsal commits). Follow-up: `benchmark/m65/pilot_universe.json` embeds v2 (stale; rebuild before any M65 use).
- **P609** (lead call): the freeze now requires a PASS receipt for the exact OFF commit (`1713bbae`; it only checked the sha's
  shape). Main-only (the freeze runs from `main`); arms unchanged.

## Worktrees / scratch (each with its resolution)

- `stack-p426-off`, `stack-p426-on` (`p426-off` / `p426-on`): the Wave 2c arms — remove after Wave 2c's harvest and the archive pushes.
  `archive/p426-wave2.v8-*-{off,on}`: superseded arms — OFF pushed with C270, ON after their gates (P606).
  `archive/p426-rehearsal.20261102a-{off,on}` (`63415dcb` / `8516cf23`): the rehearsal's arms, cited by the Wave 2c v8 — stay local (C271); record in the Wave 2c report.
- `stack-c258x-off` (`c258x-off`): keep for P577; remove after.
- `$STACK_WORKDIR/p426/wave2/` (first v8), `p426/wave2b/`, `p426/wave2c/` (all harvested; wave2c = `d23d019d` / `b6ec7819`): delete after an
  inventory table. `stack-p426-{off,on}` stay until the P606 ON gates and B6 / B8 no longer need the arm logs.
- `$STACK_WORKDIR/scratch/superseded-wave2-untracked-20261101/`, `superseded-wave2b-untracked/`, `evstage-20261101-wave2v8` (committed
  `58411357`), `evstage-20261102-wave2v8b` (committed `e18cad07`), `p586-4eyes/`, `p602-review/` (the shelved minimal patch),
  `p603-p604-review/`, `p604-universe/`, `harvest-v8b-*.txt`: delete after the push / inventory. `scratch/p594-opencode-2.2.5/`: keep for the re-pin.
- `$STACK_WORKDIR/p426/rehearsal/{20261030,…,20261102a}` + manifests + `main-clone-*`: `20261102a` is frozen into the Wave 2c v8; the rest
  delete after the inventory. `$STACK_WORKDIR/c258x/` (scrub the charger serial before any harvest).

## Rules learned (session 15)

- A push needs a PASS receipt on the exact pushed sha: gate the tip before a long run, push the gated sha (`<sha>:main`) so later docs
  commits do not invalidate it.
- An ON arm (one commit on its OFF arm) needs its own receipt; a tree identical to an ungated `main` commit is no help (P606).
- A recorded hash of a verdict is not a verdict: a precondition opens what it cites (P609).
- A version / identity bump runs the FULL gate before its arms are cut (P607: the targeted suites missed 13 pins).
- A harvest re-run re-stamps HARVEST.json (`created`, self-hash) besides the namespace paths: compare the rest byte for byte.

## Rules learned (session 14, carried)

- A guard's "fails safe" claim must hold for the largest gap the mechanism allows (DST hides exactly 3600 s; sol r2 P1).
- A default argument binds at import (`run=subprocess.run` defeated the test fakes; the "stall").
- Never put backticks in an unquoted heredoc that builds a brief (the shell runs them); a re-cut runs under `set -e`, never `;`-chained.
- File names can look like addresses (`compile@go1.27.3-…count`); a main-bound index must not list private names (P599).
- Dry-run the harvest over every real tree before relaunch (found P599).
- (Superseded by C273: tool outputs leak the wall clock; same seeds reproduce short items only, ≈ 2 % of long items flip outcome.) With frozen seeds, item behaviour repeats across attempts (`go/crypto-square` ran away identically 5 times): a rerun cures only a
  random cause (P603's pipe race), never a model-driven one (P604).
- A piped capture of a client that exits can lose its tail at the pipe buffer: capture large outputs to files (P603).
- A grader's "infrastructure" class must be attributable: protected inputs (tests, go.mod) failing = infra; the model's own files failing
  = a scored fail (P604 review).
- A planned fix may never have been built: check the code, not the ruling (C180 / P383 → P602).

Next decision id C275; discussion ids continue from P617.

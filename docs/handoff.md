# Handoff — 2026-11-01 (session 14 IN PROGRESS: P586–P593 built + accepted; first v8 harvested; arms re-cut; R1–R3 running; nothing pushed)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P595–P600, C269, P594, C268, P590–P591, C267,
P586–P589, …), the build spec `docs/specs/p586-relaunch-build.md` v1.1 and spec `docs/specs/p426-b2-tg1-wave2.md` §1, §4.3, §4.5, §5.1,
§10, §11, §16.8. Model names: FULL registry names only. Review rounds: 3 per artifact (AGENTS.md); the P586 build used all three (plan
r1, build r2 opinion, build r3 verify — `docs/reviews/p586/`).

## FIRST — verify (each "no" is a blocker)

1. Is the rehearsal sequencer still running (`bench.p426_wave2 rehearsal`, out-base `$STACK_WORKDIR/p426/rehearsal/20261101b`)? If yes,
   wait (never start anything alongside). If it exited: read `20261101b/sequence.log` and each leg's `leg.json`.
2. `main` = `0b185867` + this handoff's docs commits, ahead of `origin/main` (no push this session); `evidence` two local commits ahead
   (`c42bca0c` P566, `58411357` the first v8's evidence). `git status` clean.
3. Arms: `stack-p426-off` = `p426-off` `67375468`, `stack-p426-on` = `p426-on` `7a0817d3` (tree == `main` `0b185867`,
   `restore_diff_problems` = []); the first v8's arms kept as local `archive/p426-wave2.v8-af0711cf-{off,on}` (`5fd3c972` / `2a173f8b`).

## Next, in order

1. **Rehearsal verdicts** (`20261101b`, manifest `manifest-20261101b.json` `5d30779f…`, binding OFF `67375468` / ON `7a0817d3`): R1 off /
   on VALID with `1 + 2` Python then 2 Go items each + pilot dossier PASS; R2 INVALID for `reconciliation mismatch (injected)` ON THE FIRST
   GO ITEM, ending a clean INVALID (P588 tombstone, no chain abort); R3 VALID with a probe-kill case on the first Python item. Any other
   outcome: diagnose from the records (client export + worker telemetry, never one log line), propose, red-first.
2. **The gate on the new OFF commit `67375468`** (quiet box; never with anything else), new build inputs.
3. **The freeze needs the operator's Go**: bring the inputs (arms, rehearsal manifest + verdicts, settle bound / walls from the rehearsal,
   build inputs, gate receipt, `client_step_cap`), then `p426_freeze v8` into `$STACK_WORKDIR/p426/wave2b/records/`, then
   `p426_wave2 run --out-base $STACK_WORKDIR/p426/wave2b` (legs 1–8, ≈ 13 h; `nohup`, relative `PYTHONPATH=benchmark`, `--main-root` the
   real checkout).
4. Then (quiet windows only): C258 crossover via the fork `qualify.py --prompt-tokens` / `--max-output-tokens` flag (P577 (a)); P503 fixes
   (C261: P570 / P571 / P573 / P575 as one test-only change, P574, P572); P576 (rehearsal default main root); C269's queued opencode
   2.2.5 re-pin (B′, its own validated item).

## Session 14 instructions (operator, carried)

- Ask the operator only at Go / Accept / pushes / scope changes. "Keep the GPU busy" (session 14): launch GPU work as soon as its inputs
  exist; CPU-only work alongside a rehearsal stays light (rehearsal walls feed the settle bound).
- Rules: a push means its stated level passed (P541): read gate verdicts before any push, never chain them; one push at the end of the
  session unless the operator says otherwise. Never commit with `--no-verify`. Never run anything while a gate or GPU measurement runs.
  Tests never read live registry or box state. Numbers in docs come from generated scoresheets. Before deleting any local state: inventory
  against `main`, `evidence` and the HF dataset, file reports first, have the table verified.

## State — 2026-11-01

- **P586–P593 built** (four-eyes, `92a6fe68`; spec v1.1; cast: Claude Sonnet 5.5 implementer + fix round, Claude Opus 5.5 test-writer
  (continued), sol `gpt-5.6-sol-high` r2 opinion + r3 verify): `kill_client_aborted` under provenance (a)–(e) (close gap = export wall −
  telemetry elapsed, no local stamps), Go `go.stderr` rule + `--dry-run`, tombstone, Go rehearsal, UTC `…Z` leg stamps, `client_abort`
  block + v8 `client_step_cap`; fix round X1–X8 incl. P599 (Go telemetry names folded out of `HARVEST.json`) and P600 (`--namespace`).
  Suites 2710 passed, 5 skipped; frozen 219/219; offline replay of leg 3: all 24 item records reconcile. Declined residuals: sol-5
  (dry-run stops at a structural leg.json error), sol-7.
- **P601** (`2b25f86b`): the naming hook treats harvested Wave-2 records as data.
- **First v8 harvested** (`0b185867`, main `benchmark/results/p426/wave2.v8-af0711cf/`; evidence `58411357`); never paired.
- **C269**: opencode 2.0.20's 60-min cut stays for Wave 2b, recorded + reported per arm with a sensitivity; 2.2.5 re-pin queued.

## Worktrees / scratch (each with its resolution)

- `stack-p426-off`, `stack-p426-on` (branches `p426-off` / `p426-on`): the Wave 2b arms — archive as `archive/p426-wave2-{off,on}` at the
  push (P567), then remove. `archive/p426-wave2.v8-af0711cf-{off,on}`: the first v8's arms — push with the archives (P567), local refs only.
- `stack-c258x-off` (branch `c258x-off`): the crossover's all-OFF registry — keep for P577; remove after.
- `$STACK_WORKDIR/p426/wave2/` (first v8 out-base): harvested (main `0b185867`, evidence `58411357`) — delete after an inventory table
  (it also holds the superseded pilots' old `scratch/evidence` stage under `wave2/` paths: not to be published).
- `$STACK_WORKDIR/scratch/superseded-wave2-untracked-20261101/`: the old untracked `wave2/{pairs,run,tg1-*-pilot.a1}` copies (54 / 56
  files byte-identical in `wave2.v8-af0711cf/`, the 2 `HARVEST.json` differ by published paths) — delete with the inventory above.
- `$STACK_WORKDIR/scratch/evstage-20261101-wave2v8`: committed to `evidence` (`58411357`) — delete after the push.
- `$STACK_WORKDIR/scratch/p586-4eyes/`: the four-eyes run (copies, briefs, raw outputs; filed scrubbed in `docs/reviews/p586/`) — delete.
- `$STACK_WORKDIR/scratch/p594-opencode-2.2.5/`: the unpacked 2.2.5 bottle (strings) — keep for the re-pin item.
- `$STACK_WORKDIR/p426/rehearsal/{20261030,…,20261101a}` + manifests + `main-clone-*`: earlier attempts — one-line summary each in the
  P586 build record, harvest `20261101a`'s stage with Wave 2, delete the clones. `20261101b` + `main-clone-20261101b`: the current one.
- `$STACK_WORKDIR/c258x/` (crossover logs; the smoke block's power lines carry a charger serial: scrub before any harvest).

## Push (one, at the end of a session, operator approval)

`main` (level full: a PASS gate on its tip), `evidence` (`c42bca0c`, `58411357` + Wave 2b stages: data-only), the arm archive branches.
Read every gate verdict before the push; never chain them (P541).

## Rules learned (session 14)

- A guard's "fails safe" claim must be checked against the largest gap the mechanism allows: a DST fall-back hides exactly 3600 s, so a
  naive local difference is unsafe for any pause ≥ 1 h (sol r2 P1).
- A default argument binds at import: `run=subprocess.run` defeats every test fake of `subprocess.run` (the T3 suite read the real
  `pmset` log; the "stall").
- Never put backticks in an unquoted heredoc that builds a brief: the shell runs them (a 23-MB brief, rejected by the CLI).
- A `&&` chain that fails mid-way continues after its `;`: a re-cut step must stop the whole sequence on the first error (the ON arm
  briefly reverted the data commit; caught and rebuilt).
- File names can look like addresses (`compile@go1.27.3-…count`): a main-bound index of excluded files must not list private names.
- Dry-run the harvest over every real tree before relaunch; it found P599, which no fake tree had.

Next decision id C270; discussion ids continue from P602.

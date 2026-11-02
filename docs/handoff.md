# Handoff — 2026-11-02 (session 14 IN PROGRESS: P586–P593 built + accepted; rehearsal 20261101b all as expected; gate PASS; v8 `4104c7fc…` frozen; Wave 2b legs 1–8 RUNNING; nothing pushed)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P595–P600, C269, P594, C268, P590–P591, C267,
P586–P589, …), the build spec `docs/specs/p586-relaunch-build.md` v1.1 and spec `docs/specs/p426-b2-tg1-wave2.md` §1, §4.3, §4.5, §5.1,
§10, §11, §16.8. Model names: FULL registry names only. Review rounds: 3 per artifact (AGENTS.md); the P586 build used all three (plan
r1, build r2 opinion, build r3 verify — `docs/reviews/p586/`).

## FIRST — verify (each "no" is a blocker)

1. Is the Wave 2b sequencer still running (`bench.p426_wave2 run`, out-base `$STACK_WORKDIR/p426/wave2b`, started 2026-11-02 07:01Z,
   ≈ 13 h)? If yes, never start anything alongside (no suites, gates, builds). If it exited: read `wave2b/sequence.log`, each leg's
   `leg.json`, the pair dossiers.
2. `main` ahead of `origin/main` (no push this session); `evidence` two local commits ahead (`c42bca0c`, `58411357`). `git status` clean.
3. Arms: `p426-off` `67375468`, `p426-on` `7a0817d3` (tree == `main` `0b185867`); the first v8's arms as local
   `archive/p426-wave2.v8-af0711cf-{off,on}`.

## Next, in order

1. **Wave 2b** (v8 `4104c7fc…` in `wave2b/records/`; rehearsal `20261101b` manifest `5d30779f…`: R1 off / on VALID with Go, dossier
   PASS; R2 INVALID injected on `go/beer-song` (leg record INVALID; the chain exit was the P602 ambient-orphan refusal); R3 VALID,
   `python/beer-song` = `kill_inflight_failed`, AND `go/crypto-square` = `kill_client_aborted` — P586 live; gate PASS on `67375468`,
   receipt `df5eba89…`; settle bound 7271 s). On a stop: diagnose from the records (export + worker telemetry), propose, red-first.
2. After Wave 2b: B8 pair verification / B6 signals per spec §12 (client-cut endings per arm + the C269 sensitivity), README evidence
   update, the MTP certification call per AGENTS (per-axis signals to the operator).
3. Quiet windows after Wave 2b: **P602 = build P383 per plan v4** (four-eyes; C180's ambient-orphan rule), the gate on `main`'s tip
   for the push, C258 crossover (P577 (a)), P503 fixes (C261), P576, the opencode 2.2.5 re-pin (C269 B′).

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

Next decision id C270; discussion ids continue from P603.

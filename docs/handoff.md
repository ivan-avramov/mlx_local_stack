# Handoff — 2026-11-01 (session 13 END: Wave 2 stopped at leg 3 (INVALID); the relaunch plan v2 reviewed; build in session 14; nothing pushed)

THE one handoff. Read this, then `docs/reviews/p586/plan.md` (THE plan, v2, with its review dispositions), then `docs/open-questions.md`
top entries (newest first: C268, P590–P591, C267, P586–P589, C266, P585, C265, P584, P583, C264, P581–P582, C263, P579–P580, C262, P578–P577,
P576, C261, P570–P575, P569, P568–P563), and spec `docs/specs/p426-b2-tg1-wave2.md` §1, §4.3, §5.1, §10, §11, §16.8. Model names: FULL
registry names only. Review rounds: 3 per artifact (AGENTS.md); the plan used round 1 of 3.

## FIRST — verify the end of session 13 (each "no" is a blocker)

1. Nothing runs: no `bench.p426_wave2` / `run_tg1_chain` / `bench_watch` / `opencode run` / mlx-serve process; :8000 free.
2. `main` is ahead of `origin/main` by session 13's local commits (no push this session); `evidence` is one local commit ahead
   (`c42bca0c`, P566's log slice). `git status` clean apart from the untracked Wave-2 harvest files under `benchmark/results/p426/wave2/`
   (the first v8's pilots — they move to `wave2.v8-af0711cf/` per the plan, never committed under `wave2/`).
3. The first v8's out-base `$STACK_WORKDIR/p426/wave2/` holds `records/v8_base.json` (`af0711cf…`), `amendment.json`, the pilot pair
   (VALID, dossier PASS) and `tg1-p426-off-s1.a1` (INVALID, harvest refused: P587).

## Next, in order (C267; the operator wants this in a fresh session)

1. **Build the plan** (`docs/reviews/p586/plan.md` v2): P586 (`kill_client_aborted` + its completed-unaccounted variant, provenance-gated),
   P587 (Go grader `go.stderr` → evidence, then a dry classifier over leg 3's whole tree until clean), P588 (invalidated-slot tombstone),
   P589 (rehearsal: + s1's first 2 Go items; R2's injected mismatch on the first Go item), P590 (DST audit), P591 (record the client's
   step-cap source), P592 (an explicit client request / step timeout = the AGENTS bound, both arms), P593 (ending / speed provenance
   per arm; client-aborted endings their own runaway-tax category). Each red-first; fixtures from leg 3's real records (scrubbed). Four-eyes light (implementer + independent
   test-writer) is the user's standing preference for non-trivial work; plan review rounds 2–3 remain for the built change.
2. **Offline replay** of leg 3 through the fixed code: all 23 items reconcile (`go/crypto-square` = `kill_client_aborted`), the dry harvest
   classifier finds nothing. Then the B2 / T3 / M64 / M62 / guard suites (build pytest file lists in Python; background shells do not expand
   globs here).
3. **Harvest the superseded first v8** (pilots + leg 3) into `benchmark/results/p426/wave2.v8-af0711cf/` + `evidence`, BEFORE the new run
   publishes (plan "Records").
4. Re-cut both arms on the new `main` tip (P564 form: OFF = `main` minus C244's registry + seeding-test hunks; ON = OFF + them, tree ==
   `main`; `restore_diff_problems` = []), a new rehearsal manifest, R1–R3 (now with Go) on a fresh out-base under `p426/rehearsal/`
   (`--main-root` = a scratch clone, P576), check R1 VALID ×2 + dossier PASS, R2 INVALID for the injected reason ON THE GO ITEM, R3 VALID
   with a kill case. Then the gate on the new OFF commit (quiet box), new build inputs, `p426_freeze v8` into `$STACK_WORKDIR/p426/wave2b/
   records/`, then `p426_wave2 run --out-base $STACK_WORKDIR/p426/wave2b` (legs 1–8, ≈ 13 h; `nohup`, relative `PYTHONPATH=benchmark`).
   The freeze needs the operator's Go (C266 pattern: "review, then freeze if clean").
5. Then (quiet windows only): C258 crossover via the fork `qualify.py --prompt-tokens` / `--max-output-tokens` flag (P577 (a)); P503 fixes
   (C261: P570 / P571 / P573 / P575 as one test-only change, P574, P572); P576 (rehearsal default main root).

## Session 14 instructions (operator, session 13)

- Build P586–P593 per the plan, each red-first, fixtures from leg 3's real records (scrubbed), four-eyes light. P586 is provenance-gated:
  `kill_client_aborted` (+ its completed-unaccounted variant) only with ALL of the plan's conditions (a)–(e); everything else stays systemic.
- Offline replay of leg 3 (all 23 items reconcile; the dry harvest classifier clean), then the B2 / T3 / M64 / M62 / guard suites; then one
  cold review of the built change (round 2 of 3; cursor `gpt-5.6-sol-high`).
- Harvest the superseded first v8 into `benchmark/results/p426/wave2.v8-af0711cf/` + `evidence` before anything new publishes.
- Re-cut the arms, rehearse R1–R3 with the Go items, gate the new OFF commit; bring the freeze inputs — the operator gives Go on the freeze.
- After Wave 2 (quiet windows only): P577 (a) crossover flag, P503 fixes (C261), P576.
- Rules: a push means its stated level passed (P541): read gate verdicts before any push, never chain them; one push at the end of the
  session unless the operator says otherwise. Never commit with `--no-verify`. Never run anything while a gate or GPU measurement runs.
  Tests never read the live registry state. Numbers in docs come from generated scoresheets, never hand-copied. Before deleting any local
  state: inventory against `main`, `evidence` and the HF dataset, file reports first, have the table verified. Ask the operator only at
  Go / Accept / pushes / scope changes.

## State — 2026-11-01

- **Wave 2, first v8** (`af0711cf…`, arms OFF `5fd3c972` / ON `2a173f8b`): pilots VALID + dossier PASS + amendment; leg 3 `off-s1.a1`
  INVALID at `go/crypto-square` (a 61-min thinking runaway the client aborted — no reconciliation case, P586) after 22 Python + 1 Go items;
  superseded, never paired.
- **B2 live fixes this session** (each red-first; reviews `docs/reviews/{p579-p580,p581,p583,p585}/`): P578 worktree_state; P579 shared
  RECORD files; P580 console-script shebangs; P581 worker-argv shebang token; P582 TMPDIR harvest rules; P583 metallib via descriptor;
  P584 R3 stall-kill via the real `stalled` gate; P585 psutil SystemError in the process guard (v3 + review-r3 fix). Open: P576.
- **C258 crossover**: `run_capacity` failed its 256K anchor for `Ornith-1.0-35B-mlx-uniform-4bit` (rows committed, void); next = P577 (a).
- **P569**: the C260 cleanup lost P499's rows / log and the T3 smoke worker logs; its own inventory was not filed.
- **P566**: the Wave-2 historical walls are generated (`benchmark/results/p426/wave2/historical_walls.json`, sources on `evidence`).

## Worktrees / scratch (each with its resolution)

- `$STACK_WORKDIR/worktrees/stack-p426-off`, `stack-p426-on` (branches `p426-off`, `p426-on`): the Wave 2 arms — re-cut for the new v8;
  archive the final arm commits as `archive/p426-wave2-{off,on}` at the push (P567), then remove.
- `$STACK_WORKDIR/worktrees/stack-c258x-off` (branch `c258x-off`): the crossover's all-OFF registry — keep for P577; remove after.
- `$STACK_WORKDIR/p426/wave2/` (the first v8): harvest per step 3, then delete the scratch clone under it.
- `$STACK_WORKDIR/p426/rehearsal/{20261030,…,20261101a}` + `manifest-*.json` + `main-clone-*`: rehearsal attempts; `20261101a` bound the
  first v8. File a one-line summary per attempt in the P586 build record, harvest `20261101a`'s stage with Wave 2, delete the clones.
- `$STACK_WORKDIR/c258x/` (crossover block logs; the smoke block's power lines carry a charger serial: scrub before any harvest),
  `$STACK_WORKDIR/p426/historical/` (harvested, `c42bca0c`), `$STACK_WORKDIR/scratch/evstage-20261030-p566` (published),
  `$STACK_WORKDIR/p426/wave2/build_inputs*.json`.

## Push (one, at the end of a session, operator approval)

`main` (level full: a PASS gate on its tip), `evidence` (`c42bca0c` + Wave 2 stages: data-only), the arm archive branches. Read every gate
verdict before the push; never chain them (P541).

## Rules learned (session 13)

- Code tested only against fakes breaks on its first live run: before any first live run, a read-only shakedown of every real box op,
  and a rehearsal that covers EVERY item kind the legs run (Python AND Go) and every failure path they can take (P589).
- A diagnosis from one log line is a hypothesis: check the client's own record and the worker's telemetry before writing a rule (P586's
  first diagnosis was wrong by 60 min — the DST fall-back hour, P590).
- A spec's injection must be checked against the real mechanism (P584). Never mutate a library's shared objects (P585 v2).
- A narrowed fix is a scope change: say so in the proposal, not in a status line (P585 v1).
- Background shells here may not expand globs: build pytest file lists in Python (`glob.glob`).
- A directory is deleted only when a manifest lists its files; harvest a cleanup's own inventory first (P569).

Next decision id C269; discussion ids continue from P594.

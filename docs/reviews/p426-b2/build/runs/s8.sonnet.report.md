Slice s8 is implemented and the targeted tests pass: 480 passed in 108.37s. Nothing was committed.

## Files

**Added (all untracked; I changed, deleted and committed nothing else):**
- `benchmark/bench/p426_freeze.py`: CLI `rehearsal` / `v8` / `amend`, `main(argv, *, ops, checks)`, the three sealed exclusive-created records, the R1/R2/R3 verification, `live_problems` (v8 against the live worktrees), `write_amendment`, `deadline_formula`, `pilot_walls`, and `BoxOps` (the real ops).
- `benchmark/bench/p426_wave2.py`: CLI `run` / `makeup` / `rehearsal`, `main(argv, *, ops, clock, sleep)`, `leg_argv`, `deadline_s`, `leg_deadline`, `makeup_groups`, `canonical_occurrences`, `classify_leg`, `pilot_gate`, `read_sequence` / `write_sequence`, the `Sequencer`, and `BoxSeqOps` (the real ops).
- `benchmark/bench/tests/test_b2_s8_freeze.py`: 48 tests.
- `benchmark/bench/tests/test_b2_s8_wave2.py`: 89 tests.
- `benchmark/bench/tests/b2_s8_support.py`: a non-collected helper that builds receipts and leg roots for the two test files. It is an extra file the brief didn't name.

## Red first
- **Freeze:** with `NotImplementedError` stubs I ran `bench/tests/test_b2_s8_freeze.py`, which gave `48 failed in 0.62s`. Every failure was `NotImplementedError`, none a collection or fixture error.
- **Sequencer:** the same with stubs gave `88 failed, 1 passed in 1.33s`, again all `NotImplementedError`. The one pass is the source-text test (no `acquire("chain"`, no kill calls, no `psutil`), which is trivially true on a stub; it also passes against the real code.
- **After implementing:** freeze went `48 passed in 0.93s`. The sequencer first gave `2 failed, 87 passed`; both failures were my fixture, which wrote no `.dnf.json` item record for a DNF slot. I fixed the builder, not the code.
- **Mutation spot-checks:** I broke three behaviours (idle gap, `LAST_LEG_END` write, the pair gate in `pilot_gate`) and each turned tests red (4, 1 and 1 failures). All three were reverted.

## Commands and verbatim summary lines
- `../bin/run_stack_tests.sh bench/tests/test_b2_s8_wave2.py bench/tests/test_b2_s8_freeze.py` gave `137 passed in 3.04s`.
- `../bin/run_stack_tests.sh bench/tests/test_b2_s8_freeze.py bench/tests/test_b2_s8_wave2.py bench/tests/test_b2_s7_locks.py bench/tests/test_b2_s1_cli.py bench/tests/test_c147_chain_runner.py bench/tests/test_local_gate.py bench/tests/test_p426_wave1.py` gave `480 passed in 108.37s (0:01:48)`.
- I changed no existing module, so no other test file imports a changed module. The Wave-1 sequencer test file is in the 480 run and its behaviour is unchanged.

## Not satisfied, and why
- **Make-up mode not in the chain:** `run_tg1_chain.py` accepts only `pilot` and `chain`. It has no `makeup` mode and no `--occurrences` code path, so the argv the sequencer generates for legs 9–10 will be refused by the chain until s1/s3 adds them. Changing chain scheduling was outside s8.
- **Rehearsal shape and injections not wired in the chain:** `--rehearsal` and `--inject` are only parsed and checked. I found no code that applies the smoke shape or the R2/R3 injections.
- **No unmocked production-topology test:** spec §13 asks for one (sequencer → chain → fake probe). I wrote only the fake-ops tests; the chain-side pieces above are missing anyway.
- **Real ops are untested:** `BoxOps` and `BoxSeqOps` (git, `--print-identity`, subprocess launch, `pmset` power) were never run. The default `checks` runs `--help` on the chain and probe entry points (K3) and checks the locked mlx version in both venvs; neither check has been exercised on a real worktree.
- **Harvest contract assumed:** the default `harvest` shells out to `python -m bench.p426_harvest wave2 --leg-root … --main-root … --evidence-stage … --operator-email …`. The `--operator-email` flag, and the existence and signatures of `publish_dossier` / `publish_run_files`, are my assumptions for s9; none exist in `p426_harvest.py` yet.
- **Frozen `test_b2_frozen_*` files:** I did not read or run them. I took that to mean the verifier's blind set, and built everything from the spec.

## Judgement calls where the spec left a choice
- **R1 inputs:** the CLI takes `--r1-off` / `--r1-on` (§16.7) rather than the `--r1` in §16.2.
- **Operator-only inputs:** v8 and amend take `--build-inputs <json>` and `--historical-walls <json>` for the default ops. These carry the build label, production ref, grader image id, frozen date, suite-receipt sha and the largest historical per-item walls.
- **v8 checks:**
  - "Fork production tree == the serving build's" is checked as the gitlinks and production ref equalling `p426_plan.EXPECTED_BUILDS[build]`, with no separate tree hash.
  - `settle_bound_s` comes from the build inputs, with a 900 s floor.
  - R2 "INVALID for exactly that reason" means exactly one `p426_invalid` entry whose reason matches `reconcil` (case-insensitive).
  - R3 means VALID, no DNF, and an item record with a `kill_*` case.
- **Leg states:**
  - `OVERRUN` means the leg overran and ended without finishing and without a systemic record. An overrun leg that finishes keeps its normal state plus `overrun: true`.
  - Leg-record `class` is one of `valid`, `dnf`, `systemic`, `entry`.
  - `NOT_STARTED` is rc 2 with no `chain.json`.
  - The sequencer checks that the ledger length equals the plan (5, 43, 43, 5 per leg; the union size for make-up).
- **Stops and exit codes:** exit codes are 0 done, 1 stopped (leg, gate, pair or drift), 2 refused, 3 overrun, 4 harvest failure.
  - An unremoved `OVERRUN_PAUSED` file stops a restart.
  - A pair-dossier verdict of `FAIL` stops the sequence; the failed dossier is still written and published.
  - A low-power reading before a launch stops without consuming an attempt number.
- **Reruns:** `--rerun LEG --rerun-reason TEXT` makes a new attempt and is recorded under `reruns` in `sequence.json`. `sequence.json` also carries `harvested` and `previous_sha256`, and leg entries stay exactly `{leg, attempt, state}`. A leg found as `RUNNING` stops the run.
- **Make-up:**
  - Make-up out-roots live under `<out-base>/makeup/`.
  - I read `occurrence` as the item's ordinal in its original order.
  - Occurrences are deduplicated per (session, language, item, seed) with `arm_of_dnf` merged into a sorted list.
  - `not_run` is computed by matching ledger slots on (session, language, item).
- **Paths and rehearsal:**
  - `run` and `makeup` need `--out-base` under `$STACK_WORKDIR/p426/` and outside `rehearsal/`; `rehearsal` needs it inside `rehearsal/`.
  - Rehearsal legs get a fixed 6 h supervision deadline.
  - The rehearsal frozen date is the sequencer's clock date.
  - The rehearsal probe identity comes from `ops.identity` on the OFF worktree.
  - Rehearsal pair dossiers are written but never published, and R2 ending INVALID is expected rather than a stop.
- **Supervision:**
  - The supervision tick is 30 s.
  - The watcher starts once the leg's out-root exists.
  - After the chain exits, the watcher gets 900 s to finalize; if it hasn't, the leg is speed-invalid and the sequencer stops before the harvest, killing nothing.

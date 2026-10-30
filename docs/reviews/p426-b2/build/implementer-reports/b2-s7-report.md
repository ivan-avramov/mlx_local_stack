Slice s7 is done, but not every file you named passes: `test_c147_chain_runner.py` fails 51 tests, and I did not touch it.

All 51 fail at `run_tg1_chain.py:368` with `REFUSED: --predictor off asserts the committed entry state`, before any s7 code runs. They use `run()`'s default registry, which is now the live ON file. The same cause fails `test_m63_predictor.py` (2), `test_p311_chain.py` (41), `test_p364_chain.py` (13), `test_p371_chain_core.py` (47), `test_p371_baseline.py` (8), and 6 tests in three `test_p371_review_*_tg1` files. `test_p371_isolation.py` errors on the same thing (9 errors). Passing `registry=pinned_off_registry()` through `test_c147_chain_runner.run()` (with the same pinned-registry fix in the baseline harness) would very likely clear them, but those files are outside what you authorized me to edit. Say if you want it applied.

## Files

- **Added** `benchmark/bench/p426_locks.py`: the arbiter, the three actors' own and opposing locks, `Held`, `LockRefused`, `idle_gap_problem` and `read_last_leg_end`.
- **Added** `benchmark/bench/tests/test_b2_s7_locks.py`: 67 tests.
- **Changed** `benchmark/bench/local_gate.py`: `run` and `release` hold `gate/RUNNING` and refuse on `SEQUENCER.lock` / `LEG.lock`. `check` takes no lock.
- **Changed** `benchmark/chains/c147/run_tg1_chain.py`: `--p426` legs take `LEG.lock` before anything is created, then run the Entry row before `chain.run()`. A refusal is `REFUSED:`, rc 2.
- **Changed** `benchmark/bench/chain_core.py`:
  - New `p426_entry_row()` and `p426_ready_problems()`, plus the `P426_ENTRY_SEAMS` and `P426_POWER` constants.
  - `p426_state_problems(entry=False)` now also compares gitlinks against the v8 base's.
  - `p426_bind_router` binds the ready checks to the hooks.
  - `p426_invalidate` now writes `hook_disposition: "invalidate"` on the invocation record. A ready-stage stop otherwise leaves no `invalidate` in `chain.json`, and the frozen `test_new_a_failed_ready_check_invalidates_before_the_items_go` asserts it. This touches the s3 barrier path, so say if you want it backed out.
- **Changed** `benchmark/bench/chain_ops.py`: `ChainOps.last_leg_end()`. A garbled `LAST_LEG_END` raises `ChainAbort`, never "no previous leg".
- **Changed** `benchmark/bench/p426_hooks.py`: `bind_ready_checks`. `before_attempt` runs the bound checks, and a check that cannot run is a `HookInfrastructureError`.
- **Changed** the five fold-in tests: `test_b2_s1_cli.py` (a new `pinned_off_registry()` helper that asserts the fixture's sha256, plus four tests) and `test_b2_s2_probe.py` (one test, importing the helper).
- Nothing deleted, nothing committed.

## Commands

- Full targeted run of the named files plus s1–s6 and the related files (s7, local gate, `fix_chain`, `fix_goldens`, s1–s6, `chain_ops`, `p426_leg`): `737 passed in 81.25s (0:01:21)`. The five fold-in tests pass on their own: `5 passed in 6.93s`.
- Every failure outside those files is the registry refusal above (I read the traceback for `test_p371_baseline` and `test_p371_isolation`).
- Mutation check: with the ready-checks binding disabled, the three ready-stage tests fail (`3 failed, 1 passed`). I reverted it.
- The s7 tests were written first, but I never ran them red against the old code. My first run was after the implementation, with 66 of 67 passing; the one failure was the `hook_disposition` point above.

## Judgement calls and gaps

- The Entry busy check reads `ops.start_state()["busy"]` rather than `busy_procs()`, because the frozen entry test patches `start_state`.
- The `:8000` listener check runs only if the ops offer `listeners`. The frozen fakes lack it, and `ChainOps.start_router` refuses a listener anyway, so it is not a hard seam.
- `LAST_LEG_END` is read as one decimal epoch-seconds number. s8's sequencer must write that format.
- A refused entry leaves the attempt's out-root holding only `RUNLOG.md`.
- The Item `done` row's repeat of the registry/lifecycle/worktree checks is not added (not in the brief).
- `P426_SEAMS` is unchanged, because `test_b2_fix_chain` pins its exact contents. The new seams are in `P426_ENTRY_SEAMS`.
- My chain tests import the `b2_frozen_add_support` / `b2_frozen_support` helpers, as `test_b2_fix_chain` already does. I did not run or edit any `test_b2_frozen_*` file.
The legacy chain harnesses now serve the pinned OFF registry by default, and every file you listed passes under both the live ON registry and a swapped-in OFF copy. `main_models.yaml` is restored; `git diff HEAD --stat -- main_models.yaml` is empty.

The change was small:

- **Shared helper:** `pinned_off_registry()` and the sha256 assert now live in `test_c147_chain_runner.py`.
- **Default registry:** `FakeOps.__init__` sets `self.overlay` to the pinned copy. The runner's `served_registry` falls back to `ops.overlay`, so every harness built on `FakeOps` follows. That covers the c147, p371, p311, p364, p290, p279 and isolation harnesses, and the baseline `new_side` harness through its `T.FakeOps` subclass.

## Files changed in this follow-up

- `benchmark/bench/tests/test_c147_chain_runner.py`: adds `OFF_REGISTRY_FIXTURE`, `OFF_REGISTRY_SHA256` and `pinned_off_registry()` (the sha256 assert stays), plus `import hashlib`; `FakeOps.__init__` sets `self.overlay` to the pinned copy.
- `benchmark/bench/tests/test_b2_s1_cli.py`: drops its own copy of the helper and imports the shared one.
- `benchmark/bench/tests/test_m63_predictor.py`: `test_m3_production_wiring_off_is_the_c147_layout` now passes `registry=pinned_off_registry()` and expects that path instead of `R.REPO / "main_models.yaml"`.
- `benchmark/bench/tests/test_b2_s7_locks.py`: adds `test_no_chain_harness_serves_the_live_registry`.

## Hermeticity test

It runs a legacy chain through `run()` with no `registry=` and records what `served_registry` returns. It asserts that is the pinned copy and not `REPO / "main_models.yaml"`, and that `FakeOps().overlay` is the pinned copy. A control line asserts that without ops the runner would pick the live file, so the guard can fail. I did not run it red against the old `FakeOps`.

## Goldens

No golden or expected value changed. The one expectation I rewrote, in `test_m63_predictor.py`, was a path comparison to the live file. The p371 baseline goldens pass unchanged.

## Commands and results

- **Before the fix:** the six files outside the main set (`test_p290_docker_gate.py`, `test_p279_smoke.py`, the three `test_p371_review_*_tg1` files, `test_m63_predictor.py`) failed with 15 failures, all the live-registry refusal.
- **After the `FakeOps` change:** `test_c147_chain_runner.py`, those six, `test_b2_s1_cli.py` and `test_b2_s2_probe.py` left one failure, the production-wiring test above. `test_p371_chain_core.py`, `test_p311_chain.py`, `test_p364_chain.py`, `test_p371_isolation.py`, `test_p371_baseline.py` and `test_m63_predictor.py` then ran clean (all `.`, no failures).
- **Full list, live registry (MTP ON):** `../bin/run_stack_tests.sh` over the 18 files:
  - the 12 files you listed
  - `test_b2_s7_locks.py`, `test_b2_s1_cli.py`, `test_b2_s2_probe.py`
  - `test_local_gate.py` (the only match for `test_local_gate*.py`)
  - `test_b2_fix_chain.py`
  - `test_t3_wave1.py`
  - Result: `791 passed in 442.96s (0:07:22)`
- **Same list with the pinned OFF copy copied over `main_models.yaml`:** `791 passed in 446.16s (0:07:26)`.

I did not run `test_m61_web_audit.py` or the full suite, and I did not touch non-test code, frozen files, `src/` or the spec.

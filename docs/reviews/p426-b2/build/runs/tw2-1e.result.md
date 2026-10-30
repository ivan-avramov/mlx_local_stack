## Delivery 1e report: the set, amended and aligned for re-freezing

I amended the frozen files where §16.5 / §16.6 invalidated them, aligned the `add_` files with §16.6, and added the rehearsal-leg key test. The set is ready for the designer to freeze again; I found no gaps or contradictions left in the spec.

- **Support checks:** both pass on the baseline (frozen s0: 42/42; `add_` check: 8/8).
- **Frozen set:** 244 fail and 9 pass. The 9 passes are invariants that hold on the base commit.
- **`add_` files:** 55 fail and 1 passes (also an invariant).

Every failure is a missing module or interface, or the base chain refusing `--p426`. None is a fixture error.

Nothing is committed. The working tree holds only untracked test files and the designer's spec change.

## Frozen tests and fixtures I amended, and why

| File | What changed | Why |
|---|---|---|
| `b2_frozen_support.py`, `p426_world` | Added `expected_worker_argv` (mlx-serve's own builder), `busy_procs()` (no other process), `descendants(pid)` (empty), and `create_time(pid)`, which now answers the owned worker's own start time (the router: 1.0). | §16.5 / §16.6 seams. Without them, the 29 frozen s7 chain tests would fail with `AttributeError` once s5 / s7 land, or the census would treat the owned worker as foreign. No test bodies changed; the s7 tests (and the s4 / s5 tests on this world) now meet the real checkpoints. |
| `b2_frozen_support.py`, new `a4_gate_doc` | The `gate.json` builder (`session_pinning_gate.py:284-304`). The `add_` support now imports it rather than keeping its own copy. | Needed for the 3-argument A4 tests. |
| `test_b2_frozen_s4_reconcile.py`, helper `a4_lines` | Its `anon` parameter is now a list of `(session, cached, prompt)` instead of a count; new helper `a4_gate()`. | So the bare requests can be checked against `gate.json`. |
| s4, `test_new_the_a4_window_matches_its_receipt` | Now calls `a4_window_problems(lines, a4_receipt, a4_gate)`. | §16.5 signature; the 2-argument call would raise `TypeError`. |
| s4, `test_fix_an_a4_window_whose_session_differs_from_its_receipt_is_a_problem[prompt|session|missing]` | Same 3-argument call. | Same. |
| s4, new `test_fix_an_a4_window_whose_bare_requests_differ_from_gate_json_is_a_problem[missing|prompt|session]` | New test. | The anon check §16.5 restored. |
| `test_b2_frozen_s0_support.py`, 2 new tests | `test_the_p426_world_carries_the_section_16_5_seams_and_the_owned_start_time`, `test_the_gate_json_builder_follows_the_gates_writer` | So every amended fixture is validated on the baseline. |

## 1. Per file: changes since delivery 1d

Outcomes for everything else are as in the 1c and 1d reports.

- **`b2_frozen_add_support.py`:**
  - `SeqOps.harvest(leg_root, *, emails)` records the emails (§16.6);
  - handles carry `pid` / `start` / `argv` and liveness is `alive(handle.pid, handle.start)`, as I had already chosen;
  - `world()` gains `rehearsal=`;
  - `a4_gate_doc` is now the frozen one.
- **`test_b2_frozen_add_support_check.py`:** 8 INV, all pass. The fake harvest now records its emails.
- **`test_b2_frozen_add_sequencer.py`:** 23 tests, all NEW, all F with `:22 ImportError: … 'p426_wave2'`. Changes:
  - **pair dossiers:** at `<out-base>/pairs/*.json`;
  - **`OVERRUN_PAUSED`:** at `<out-base>/OVERRUN_PAUSED`, as `{leg: off-pilot, attempt: 1, deadline_s: 4000, at}`;
  - **watcher death:** the leg record has `speed_valid: false` and a `speed_reason`, and the state stays VALID;
  - **new test, a speed-valid leg:** it records `speed_valid: true`;
  - **new test, operator email:** each harvest gets the main checkout's `git config user.email`. The test sets a fake global identity through `GIT_CONFIG_GLOBAL` / `GIT_CONFIG_NOSYSTEM`; the copy has no repo-local email, which I checked without printing a value.
- **`test_b2_frozen_add_pair.py`:** 6 tests, all NEW, all F (`:31`, `:76`, `:90 AssertionError: 2`). New test: a rehearsal leg (`chain s1 --rehearsal`) given a key over `--hmac-fd` runs, and its receipt's `HF_TOKEN` HMAC equals HMAC-SHA256 under that exact key.
- **`test_b2_frozen_add_scrub.py`:** 4 tests, 1 P / 3 F (`:29 TypeError: Scrub.__init__() got an unexpected keyword argument 'emails'`). A refusal must now be `p426_harvest.HarvestError`, publish no `HARVEST.json`, and leave the address out of both the published bytes and the error message.
- **Unchanged:**
  - census: 3 F;
  - ledger: 3 F;
  - A4: 7 F (`ImportError`);
  - argv / pins: 6 F;
  - `RECORD`: 4 F (`AssertionError: ChainOps.interpreter_inventory (§16.2) is missing`).

## 2. Commands and summary lines (verbatim)

```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py
42 passed in 16.26s

../bin/run_stack_tests.sh bench/tests/test_b2_frozen_add_support_check.py
8 passed in 0.45s

../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s1_cli.py bench/tests/test_b2_frozen_s2_probe.py bench/tests/test_b2_frozen_s3_core.py bench/tests/test_b2_frozen_s4_reconcile.py bench/tests/test_b2_frozen_s5_receipt.py bench/tests/test_b2_frozen_s6_watch.py bench/tests/test_b2_frozen_s7_locks.py bench/tests/test_b2_frozen_s8_freeze.py bench/tests/test_b2_frozen_s9_harvest.py -rA --tb=line
244 failed, 9 passed in 9.17s

../bin/run_stack_tests.sh bench/tests/test_b2_frozen_add_sequencer.py bench/tests/test_b2_frozen_add_pair.py bench/tests/test_b2_frozen_add_census.py bench/tests/test_b2_frozen_add_ledger.py bench/tests/test_b2_frozen_add_a4.py bench/tests/test_b2_frozen_add_argv.py bench/tests/test_b2_frozen_add_scrub.py bench/tests/test_b2_frozen_add_record.py -rA
55 failed, 1 passed in 0.64s
```

## 3. Remaining gaps

None that block re-freezing. One thing the implementer needs to know: the sequencer tests depend on the classification inputs §16.6 now names (rc, `chain.json`, the item records' draft counters, `watch.jsonl`'s `exit_state`, and the rows named in `progress.invocations`). A sequencer that also requires other files would fail those tests for fixture reasons.

## 4. Possible errors or contradictions in §16.6

None found. With the amended `p426_world`, I know of no frozen test that still contradicts §16.5 or §16.6.

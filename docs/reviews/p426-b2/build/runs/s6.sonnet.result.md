Slice s6 is implemented and the targeted tests pass. The 41 test files I ran, including the new `test_b2_s6_watch.py`, gave `1085 passed in 822.02s (0:13:42)`, exit code 0. They are my new file plus the existing ones that import `chain_core` or `bench_watch`. I did not run the full suite and did not commit.

## Files
- **`benchmark/m1/bench_watch.py` (changed):** adds the P426 mode (`--chain-json --driver-pid --out`, plus `--planned`, `--pred-s`). It writes one journal line per tick, then one `exit_state` line. It also adds `speed_verdict(path)`, `pair_speed(legs)`, `parse_battery_log(text, now=)`, `pmset_power()` and `read_journal`. `main(argv, *, power=None, clock=None, sleep=None)` has `sleep` as an extra injectable. The legacy loop and its flags are unchanged; `--models/--bench/--total` and the driver flag are now checked after parsing rather than by argparse, and missing ones still exit 2.
- **`benchmark/bench/chain_core.py` (changed, P469 only):** `Chain.watch_rows` now prefixes bare prior ids with `lang/`. `prior_rows` keeps bare item names while rows carry `lang/item`, so the earlier invocation's rows were filtered out; that is why the pilot's 1 row read 0. The new test failed before the fix and passes after.
- **`benchmark/bench/tests/test_b2_s6_watch.py` (added):** 35 tests, written before the code.
- **`p426_reconcile.py`:** not changed. s4's `decode_time` and `decode_rate` already handle 0-token, 1-token and `ΔD ≤ 0` requests, so I only added the per-item cases to the s6 tests. Nothing was deleted.

## Commands
- `../bin/run_stack_tests.sh bench/tests/test_b2_s6_watch.py` before any code: `30 failed, 5 passed in 0.97s`.
- The same three-file command after my first implementation: `5 failed, 90 passed`, all five from a bug in my own test helper, fixed afterwards.
- The final regression run:
  - **Files:** the s6, p426_bench_watch and s4_reconcile tests plus every non-frozen test file importing `chain_core` or `bench_watch`, and `test_c147_chain_runner`.
  - **Result:** `1085 passed in 822.02s (0:13:42)`.

## Not satisfied, or judgement calls
- **`pmset -g log` format:** `parse_battery_log` is tested only on a synthetic sample, because the real `pmset` is off-limits in tests. The `Using AC/BATT` line pattern is from memory of the real format and has not been checked against a live log. Treat it as unverified until the first rehearsal.
- **Planned slots:** `chain.json` does not hold the leg's full plan before the later invocations register. Without `--planned N`, the planned count is the slots registered so far, so progress reads 5/5 after the pilot and grows later. The s8 sequencer should pass `--planned`.
- **Exit-line fields:** I followed the field names in the frozen fake's journal (`exit_state: "driver_exited"`, `battery_intervals`, `at`, `watts`, `volts`, `battery`, `driver_alive`). I only read that fixture's data format, not the frozen s6 test, which I did not read. I added `t`, `interval_s`, `window`, `speed_valid` and `speed_reason`. `speed_verdict` fails closed on journal lines with no parseable time, so s8's fake journal (`at="t0"`, no `t`) would verdict invalid there.
- **Driver binding:** the driver's start time is bound from `ps -o lstart=`, which has one-second resolution. The spec says pid plus start time, not which clock.
- **Out of scope:** the sequencer's polling of the watcher's pid and start time (s8), and the `leg.json` `speed_valid` and `speed_reason` fields.

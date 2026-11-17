The tests are written and run on the baseline `0424892c`. 39 of 69 fake-harness tests and the 5 spin tests are red. The 30 fake-harness tests and 4 variant tests that guard unchanged behaviour are green. Nothing ran against a candidate fix, so the fake's read-back path is unexercised.

Files, all inside the copy:
- `benchmark/bench/tests/test_tg2_grade_timeout_fe_fake.py`
- `benchmark/bench/tests/test_tg2_grade_timeout_fe_docker.py`
- `benchmark/bench/tests/fixtures/tg2_grade_timeout_fe/summary_expected.json`: the `SUMMARY.json` rows minus the recorded `spin` row, which is the bug.

Every command was `../fe_test.sh stack <file>` with full output in `../scratch/` (`fake1.txt`, `fake2.txt`, `docker1.txt`, plus `probe1.txt` and `probe2.txt` for the timing probe). I used a temporary probe test for the timeout sweep and deleted it.

## Results on the baseline

| File | Tests | Red (a) | Green (b) | Seam-dependent (c) |
|---|---|---|---|---|
| fake | 69 | 39 | 30 | 12 (inside the red/green counts) |
| docker | 9 | 5 | 4 | 1 |

**Fake harness (`..._fake.py`, 15.9 s).** I did not edit `test_tg2_grade.py`.
- **How the fake works:** `BoxFakeGuard` subclasses the existing `FakeGuard`. A timed-out step leaves its stdout empty. The marker file exists only if the script text writes `/report/.tg2-marker-<step>-<nonce>`, so the fake follows the script rather than assuming the fix.
- **Read-back step:** the fake runs the read-back script on the host with `/report` and `/work/slug` mapped to the volume directories. That avoids assuming the script's marker tag or output format.
- **Red (39), on the missing marker or out file or the missing read-back:**
  - the timeout-to-`timeout` cases for compile and execute in all 4 languages (8 tests)
  - collect timeout (3)
  - the script contains the marker and out file names with the nonce (4)
  - marker file written before the compiler or runner is invoked (8)
  - fresh nonce per grade
  - read-back shape
  - out-file cap
  - `<step>.marker` and `<step>.out` stored with sha256 (2)
  - stream lost but file present
  - `VERSION == "m65-tg2-v3"`
  - the box-fact self-check (2)
  - the real-script tests on the host with stubbed compilers (7, listed under the seam-dependent class below)
- **Green (30), guarding unchanged behaviour:** no read-back on ordinary grades, the G13 cases (no marker anywhere, forged stream marker, wrong-nonce file, other step's file), unchanged outcome classes, and a failed read-back staying `TransportAbort` with its container removed.
  - The failed-read-back tests (9) are vacuously green on the baseline, because it aborts on the empty stream first. They only discriminate once the marker file exists.

**Docker (`..._docker.py`, 99.9 s total).**
- **Spin tests (red):**
  - All 4 spin tests (`test_a2_a_solution_that_spins...`) fail with the real bug: `tg2 execute: runner-start marker absent (rc=None)`.
  - The second spin test, `test_a2_the_marker_in_the_retained_file_carries_the_nonce...`, is also red.
- **Variant test (green):** `test_a3_recorded_variants_classify_as_in_summary_json` passes for all 4 languages. It re-grades reference, stub, compile and tampered for each item, plus Rust `alloc` (oom) and `flood` (output_cap). All rows match `SUMMARY.json` (outcome, reason, leaves, failing).
- **Wall time per docker test on the baseline** (spin tests aborted early, so their post-fix times will be longer by the read-back):

| Test | Seconds |
|---|---|
| spin, java | 11.9 |
| spin, cpp | 11.8 |
| spin, rust | 4.9 |
| spin, javascript | 4.7 |
| marker-nonce test (Rust) | 4.9 |
| variants, java | 25.7 |
| variants, rust | 14.0 |
| variants, cpp | 10.9 |
| variants, javascript | 10.7 |

## Measured step timeouts

I swept the reference trees, two runs per value (`probe2.txt`):

| Language | Smallest value that passed | Test uses |
|---|---|---|
| rust | 1 s | 2 |
| javascript | 1 s | 2 |
| java | 6 s (4 s flaps) | 6 |
| cpp | 5 s (3 s fails) | 6 |

Java and C++ get one integer step of margin because their compile takes 3.8–5.5 s. The baseline also aborted on a compile timeout once for Java at 4 s and once for C++ at 3 s, which is the same bug on the compile step. These values and the sweep are recorded in the docker file's docstring.

## Seam-dependent tests (c)

- **Collect timeouts:** the spec says "stdout lacks the marker", but collect's marker is on stderr. I assumed the same rule applies, so a collect timeout with the marker only in the file becomes `timeout`.
- **Phase-record key names:** these are open. The tests look for the two sha256 digests as values in the step's phase record.
- **Real-script tests (7):** they run the compile and execute scripts on the host with a stubbed `cargo` or `./gradlew` and kill the process group. They assume the scripts run under `bash -c` with `/report` as a plain path substitution. Their result is also subject to the host-execution assumption above.
- **Rust partial output:** the spin test requires `Running` in `execute.out` for Rust only. The other three languages only require the file to exist.

## Things the designer should know

1. **Conflicting existing assertion.** `test_raw_outputs_retained_by_sha256_with_phase_records` asserts `tg.VERSION == "m65-tg2-v2"`, which contradicts the v3 bump. The spec says "without changing any existing assertion", so this needs a ruling.
2. **Existing adjacency test.** `test_execute_script_prints_the_marker_right_before_the_runner_with_a_fresh_nonce` expects `echo "TG2_RUNNER_START <nonce>"; bash ./gradlew` back to back. A file write placed between the echo and the runner would break it. The marker-file write has to go before the echo or inside the same command.
3. **Spin trees are built, not copied.** The recorder directory holds receipts only, not source trees, and the polyglot corpus is outside my readable directories. So I built the spins from the reference by regex injection, as the spec allows, and did not commit the recorded trees as sha-pinned fixtures. The injected loops are an `if (nanoTime() > 0)` guard for Java, a lambda initializer for C++, `loop {}` at the top of every `pub fn` for Rust, and `while (true) {}` for JavaScript.
4. **Fake's read-back path untested.** No candidate exists yet. If the first candidate fails the read-back tests, check the fake's host-execution assumptions before blaming the candidate.
5. **No leftover check.** I could not list docker objects (command needed approval). The variant tests assert no leftovers and passed.
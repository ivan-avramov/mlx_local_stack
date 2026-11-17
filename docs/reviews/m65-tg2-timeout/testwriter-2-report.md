**Verdict: fix then merge.** I found no defect against the spec. The one fix I ask for is D6, the 5-minute always-on regrade test, below.

## 1. The 44 failures: all my test's seams, none a candidate defect

| Group | Tests | What was wrong | Action |
|---|---|---|---|
| A. Method collision | 34, incl. `test_g13_*` and the `test_a1_*` timeout/read-back tests | My `BoxFakeGuard._readback(cmd, script, kw)` shadowed the candidate's new `FakeGuard._readback(cmd, kw, spec)`. The resulting `AttributeError` was swallowed by `_grade_steps` (it catches `AttributeError`), so collect timeouts showed up as `crash`. | Amended: renamed mine to `_box_readback` / `_box_marked`. Read-back is now detected from the script text instead of `step_of`, which the candidate's harness edit changed. |
| A′. macOS `tar` | 14 tests masked by A | Host `bsdtar` added `._<name>` AppleDouble members, which the candidate's strict `parse_readback` correctly refuses. | Amended: `COPYFILE_DISABLE=1` in my host run. |
| A″. Box-fact self-check | 2 | I read the marker file after the volume had been removed at cleanup. | Amended: the fake records the file content as it writes it. |
| B. `test_a1_timeout_after_a_real_marker_in_the_stream…` | 1 | It relied on the old harness leaving a stream marker on a timed-out step. The candidate's harness now follows the box fact. | Amended: a `stream_marker` plan key on my fake. The intent is kept: no read-back when the stream has the marker. |
| C. Collect `.out` | 3 | I asserted `.tg2-out-collect-*` in the collect script. The spec says the out file is the `_bounded` output, and collect's stdout is a tar stream, so D2 is spec-consistent. | Amended: out file required for compile and execute only. |
| D. Host `stdbuf` | 4 | The macOS host has no GNU `head`, so `stdbuf -o0 head` doesn't unbuffer and a kill loses the output. | Amended: a `stdbuf` shim (`dd bs=1`) stands in for the image's. The real behaviour is proven by the docker spin tests (see section 2). |
| E. Docker `test_a2_the_marker_in_the_retained_file…` | 1 | It expected `compile.marker`, but compile finished with its stream marker, so the spec runs no read-back. | Amended: it now asserts the compile files are absent. I kept the sha256, `VERSION` and retained-files checks. |

**Marker placement.** The candidate writes the marker file immediately before the stream echo: `echo > /report/.tg2-marker…; echo "TAG n"; runner`. That keeps the spec's "marker before the runner" guarantee. Both writes are unconditional, with no `set -e` and nothing between them and the runner. The existing adjacency test still matches `echo "…"; bash ./gradlew` and passes.

## 2. Runs on the candidate

I ran docker files one at a time and ran the full `test_tg2_grade.py` docker set in the same pass.

| File | Result | Wall time |
|---|---|---|
| `fe_fake` (mine) | 69 passed | 16 s |
| `fe_docker` (mine) | 9 passed | 103 s |
| `impl_docker` | 8 passed | 70 s |
| `impl_fake` + `fe_fake` + `test_tg2_grade.py`, `-m "not docker"` | 584 passed, 21 deselected | 24 s |
| `test_tg2_grade.py`, `-m docker` | 21 passed, 0 failed | not extracted per test; slowest java reference tests 23–24 s |
| `impl_regrade`, run once | 1 passed | 304 s |

- **Docker wall times (mine):**

  | Test | Seconds |
  |---|---|
  | spin, java | 12.4 |
  | spin, cpp | 12.2 |
  | spin, javascript | 5.1 |
  | spin, rust | 4.9 |
  | marker-nonce test (Rust) | 5.1 |
  | variants, java | 28.2 |
  | variants, rust | 12.9 |
  | variants, cpp | 11.6 |
  | variants, javascript | 10.5 |

  My spins use step timeouts of 2/2/6/6 s (rust/javascript/java/cpp). All four pass, including the retained partial output (Rust `execute.out` contains `Running`).
- **Implementer docker wall times:**

  | Language | Reference | Spin |
  |---|---|---|
  | rust | 2.8 s | 7.8 s |
  | javascript | 3.6 s | 8.0 s |
  | cpp | 6.5 s | 14.0 s |
  | java | 10.5 s | 16.5 s |

- **Regrade:** all 19 rows match `SUMMARY.json`. The Rust spin moved from `transport_abort` to `timeout` with 19 of 19 failing.
- **Caveats:**
  - I did not run the full `bench/tests` suite.
  - I did not list docker objects directly. The docker tests' own leftover assertions passed.
  - The impl fake tests were exercised only in the combined non-docker run (584 passed).

## 3. Review of the candidate against the spec

- **Fix and rule:** all spec bullets are met.
  - The marker and out files are written before the runner.
  - One bounded read-back runs on the same volumes, with its own stderr marker and its own 120 s timeout.
  - `<step>.marker` / `<step>.out` and both sha256 values are stored.
  - The marker is read from the stream or the file, using the exact nonce only.
  - A failed read-back is `TransportAbort`.
  - `VERSION` is v3.
  - The `parse_readback` check (regular files with exactly the expected names, size cap) is stricter than the spec asks for.
- **D1 (`stdbuf -o0 head | tee`):** accept. It is needed, because the real-image spin run showed a plain `head` before `tee` leaves `.out` empty. The `stdbuf -o0 true` preflight turns a missing `stdbuf` into infrastructure, which avoids a false `compile_failure` via SIGPIPE.
- **D2 (collect has no `.out`):** accept, as in group C. `out_sha256` is `null` for collect.
- **D5 (extra `<step>-readback` phase record):** accept.
  - It appears only on the read-back path.
  - The one non-test consumer of phase records, `m65/tg2_universe.py:113`, sums `seconds`, so it adds a fraction of a second to timeout grades.
- **D6 (5-minute always-on regrade test): fix before merge.**
  - It runs the Rust spin at the universe's 180 s timeout, so 300 s of the 304 s is one wait for a classification that a short timeout proves identically.
  - Recommendation: in `test_tg2_grade_timeout_impl_regrade.py`, give the `spin` variant a short timeout (5 s, as the implementer's own spin test already uses). That brings it to roughly 30 s without losing the 19-row comparison. Counterpoint: the 180 s timeout is the recorder's exact method. The classification is identical either way, and the implementer's own docker spin test covers it at 5 s.
- **Gate note, not a defect:** `tg2_grade.py` and its preflight text change, so the tg2 universe freezer closure rotates again. The commit log shows this re-freeze (S25-P2) is already planned.

My amended files are `test_tg2_grade_timeout_fe_fake.py` and `test_tg2_grade_timeout_fe_docker.py`. Outputs are in `../scratch/d2_*.txt`.
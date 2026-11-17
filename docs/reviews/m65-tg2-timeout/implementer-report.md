# M65 tg2 grader — timeout keeps its start evidence — implementer report (spec v1, baseline 0424892c)

Status: DRAFT, written while the final runs were going (see "Final runs" at the end).

## Files

- `benchmark/bench/tg2_grade.py` (changed): `VERSION = "m65-tg2-v3"`. Compile and execute scripts write `"<TAG> <nonce>"` to `/report/.tg2-marker-<step>-<nonce>` immediately before the stream echo, and collect does the same before its stderr echo. `_bounded(script, evidence)` also writes the capped output to `/report/.tg2-out-<step>-<nonce>` (`stdbuf -o0 head -c CAP | tee FILE | head -c CAP`). New: `_readback_script` / `parse_readback` / `_marker_evidence`. One bounded read-back step (`<step>-readback`) runs on the same volumes, with its own stderr marker `TG2_READBACK_START <rnonce>` and its own timeout (`READBACK_TIMEOUT = 120`). It stores `<step>.marker` / `<step>.out` and adds `marker_sha256` / `out_sha256` / `marker_source` to the step's phase record. Preflight gains `stdbuf -o0 true`.
- `benchmark/bench/tests/test_tg2_grade.py` (changed, fake harness only, no assertion touched): `step_of` recognises `readback`. Compile, execute and collect write the marker / out files when the script names them (unless `no_marker`; `file_marker` forges the file content). The box fact: a timed-out marked step leaves its streams EMPTY. New `_readback` emulation with options `timeout` / `rc` / `no_marker` / `raise_os` / `tar`.
- `benchmark/bench/tests/test_tg2_grade_timeout_impl_fake.py` (new): acceptance 1, 40 tests.
- `benchmark/bench/tests/test_tg2_grade_timeout_impl_docker.py` (new): acceptance 2, 8 docker tests (reference-at-timeout ×4, spin ×4).
- `benchmark/bench/tests/test_tg2_grade_timeout_impl_regrade.py` (new): acceptance 3, 1 docker test (recorder method vs SUMMARY.json).
- `benchmark/bench/tests/fixtures/tg2_grade_timeout_impl/js-spin/word-search.js` (new): the recorded JS repro's solution, sha256 `826d156c…dcc`.
- `benchmark/bench/tests/fixtures/tg2_grade_timeout_impl/recorded_SUMMARY.json` (new): copy of the recorder's SUMMARY.json, sha256 `8ba69de7…e8ce`.

## Commands and results (full outputs under `../scratch/`)

| file | command (all `../fe_test.sh stack …` from the copy) | result |
|---|---|---|
| baseline_tg2_files.txt | the 6 files importing tg2_grade (test_tg2_grade, test_p371_review_r6_f23, test_p445_tg2_root, test_tg2_fixtures, test_tg2_materialize, test_tg2_universe), docker included, before any edit | 707 passed, rc 0 (no summary line printed; 707 dots, exit 0) |
| red1_fake_on_baseline.txt | impl_fake + test_tg2_grade, `-m "not docker"`, after the fake edit, grader unchanged | 27 failed / 484 passed: 24 new impl tests red; 3 existing tests red under the box fact (`test_timeout_after_launch_is_a_model_outcome[compile/execute]`, `test_g22_…[over0-timeout]`) |
| green1/green2_fake.txt | same, after the fix (green1 exposed a bug in my own test's assertion, which I fixed) | green2: 1 failed / 510 passed |
| green3_fake.txt | same, after the stdbuf change (+ preflight test) | 1 failed / 514 passed: only `test_raw_outputs_retained_by_sha256_with_phase_records` (pins `"m65-tg2-v2"`, see D3) |
| measure_ref_300*.txt | impl_docker reference tests at a 300 s timeout (tries 1–2 blocked by a concurrent grader's labelled objects, see Q1) | try3: 4 passed, 23.3 s |
| docker_impl_run1/2.txt | impl_docker | run1: blocked by concurrent objects; run2: references 4 passed, spins 4 failed (`.out` empty → D1) |
| docker_impl_run3.txt | impl_docker after the stdbuf change | 8 passed, 72.7 s |
| regrade_recorded.txt | impl_regrade | see below |

Per-docker-test wall (run3): reference rust 2.9 s, javascript 4.0 s, cpp 6.7 s, java 11.2 s; spin rust 7.9 s, javascript 8.4 s,
cpp 14.6 s, java 16.8 s.

Step timeouts used for the spins (measured reference step seconds at 300 s, compile / execute): rust 5 s (0.53 / 0.37),
javascript 5 s (0.60 / 0.69), cpp 8 s (3.49 / 0.27), java 10 s (3.93 / 4.17). Each run re-proves them: the reference must
compile and pass at that timeout. I did not search downward below these values; they are about 2× the slowest step.

## Deviations (with the code fact)

- D1 — the `.out` copy goes through `stdbuf -o0 head -c CAP | tee FILE | head -c CAP`, not `head -c CAP | tee FILE`. Fact (box, docker_impl_run2): with a plain `head -c` before tee, the `.out` file of every killed spin was 0 B while the marker file survived. GNU head writes through stdio, so into a pipe it keeps small output in its buffer, and the kill loses it. That is probably also why the stream is empty on the box. The trailing buffered `head -c` keeps the stream path as it was (the box fact is preserved, so the read-back path is the one exercised). Preflight checks `stdbuf -o0 true`, so a missing stdbuf is infrastructure. Without that check it would turn into SIGPIPE → rc 141 → a false compile_failure.
- D2 — collect writes only a marker file, no `.out` file. Its stdout is the report tar stream, not `_bounded` output; teeing it would duplicate up to 32 MB into the 64 MB report volume. The read-back still runs for collect, and its `out_sha256` is `null`.
- D3 — `test_tg2_grade.py::test_raw_outputs_retained_by_sha256_with_phase_records` asserts `tg.VERSION == "m65-tg2-v2"`. The spec requires the bump to v3 and forbids changing existing assertions, so this test now fails. That is a new failure against the recorded baseline (acceptance 4). Recommendation: in the gate, change the literal to `"m65-tg2-v3"`. Counterpoint: the spec owner may want the pin moved together with the universe re-freeze (S25-P2), not in this change.
- D4 — the Rust spin is built in-test (polyglot reference + the recorder's `zz_spin` block), not committed as a tree. The inputs keep only the grader outputs of the recorded Rust spin, not its source tree. The JS repro is committed as its single differing file, sha-pinned. The test rebuilds the prepared stub and asserts that the full tree's per-file sha256 equals the recorded tree's 7 files. Not committed: `.npmrc` (the harness classes it as a credential-bearing file; its content is `audit=false`). It comes from the polyglot stub and is sha-pinned.
- D5 — the read-back step's name is `<step>-readback`. It appears in `phases` and its stdout/stderr files are kept like any step's, so a timeout grade now has one more phase record.
- D6 — spec asks for acceptance 3 by "re-grade with the recorder's method". I could not run the recorder script itself (only `../fe_test.sh` is executable for me), so `test_tg2_grade_timeout_impl_regrade.py` reproduces its method line for line inside pytest. It is docker-marked and always runs when docker is available (about 5 min). I could not make it opt-in by env var, because env-prefixed commands were refused here. The gate owner may drop or mark it.

## Not satisfied / open

- Red-first for acceptance 2 is shown by the recorded baseline trees (SUMMARY.json: Rust spin `transport_abort`, plus the JS repro's keep `outcome: infrastructure`). I did not run my docker tests against baseline code.
- Q1 — the box had another tg2 grader running concurrently: labelled holders / volumes from a process outside this copy. Because `list_leftovers` is box-global, my runs aborted until it finished. My grades may also have blocked that process while they ran. I listed only, never removed anything. Gate runs need a quiet box.
- Known limit (spec): the solution can delete or forge the marker file. Unchanged.

## Final runs

- final_other5_nondocker.txt: test_p371_review_r6_f23, test_p445_tg2_root, test_tg2_fixtures, test_tg2_materialize and test_tg2_universe, `-m "not docker"`: 139 passed, 34.6 s. The v3 bump breaks nothing there.
- green3_fake.txt (above): test_tg2_grade non-docker plus impl_fake: 514 passed, 1 failed (D3).
- Not re-run at the end: the docker-marked tests of `test_tg2_grade.py` with the change (the baseline run included them). Not enough time was left, and the box was shared (Q1). The designer's gate must run them.
- regrade_recorded.txt, acceptance 3: MET. 1 passed, 307 s.
  - All 19 rows equal SUMMARY.json, except the rust/say spin row, which moved from `transport_abort` to `timeout` with all 19 leaves failed (as the spec intends).
  - Matching rows include alloc `oom`, flood `output_cap`, JS compile `parsed` 1/23, and C++ stub `compile_failure`.
  - Updated after the report deadline: an earlier draft of this line said the run was still in progress.
- Red-first for the docker tests: not run against baseline code (see "Not satisfied").

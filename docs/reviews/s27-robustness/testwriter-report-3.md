# Test-writer report, delivery 3 — S27 harness robustness bundle, fix round 1 (candidate 2)

**Verdict: merge.** Every adopted finding I could test is resolved on candidate 2. My set is 269 tests: 269 pass on candidate 2, and 155 fail / 114 pass on the baseline copy. The existing-test families show no failure caused by the fix, only failures that were already environmental. Minor findings are listed below and none blocks the merge.

## 1. My tests

Files: `test_s27_fe_{reconcile,ownership,offsets,positives,done_hook,chain,grader,harvest_view,push_binding,support}.py` plus the new `test_s27_fe_r1.py`, and fixture `fixtures/s27_fe/sgf_parsing_d1.json`. The fixture sha is re-pinned to `73f1b2cf61c4d3532b4d3a9862bd2884e3660217fd558b6b5e95b7da917a3aa9`.

Candidate 1 could not be run, because nothing may be reverted. Where a new test would have failed on it, I say "checked by inspection" and cite the fix diff.

### 1.1 Amended in this delivery

| test (file) | class / item | change | baseline | cand. 2 |
|---|---|---|---|---|
| `grader::test_an_interim_grader_infrastructure_fault_while_the_client_generates_ends_the_probe_with_the_typed_stamp` (replaces the v2 test) | (a) §10.1 interim fault → one rerun (X3) | a lingering fake client keeps generating while the interim grade faults; the test asserts no row, no final grade, `cause: grader_infra`, and that it ends in under 25 s | fail | pass |
| `grader::test_an_interim_grader_fault_first_seen_after_the_client_exited_never_costs_the_finished_generation` (new) | (a) X3 | the interim grade fails only once `GradeWorker.finish` has begun (a deterministic event gate); expected: row passed, one final grade, one generation, `termination.interim_grade_fault` recorded, no stamp | fail | pass |
| `grader::test_agent_controlled_output_that_looks_like_an_infrastructure_fault_is_never_one` (new) | (b) X6 | a plain `TransportAbort` that embeds "Connection refused / Cannot connect to the Docker daemon / docker command failed" is one grade, no regrade, no `grader_infra` stamp | pass (the baseline has no regrade) | pass |
| `grader::test_a_grade_that_returns_a_model_outcome_whose_report_names_a_docker_fault_is_just_the_outcome` (new) | (b) X6 | a returned graded result is never inspected for fault text | pass | pass |
| `support::infra()` | X6 | returns `GraderInfraError(kind="transport")` when the class exists, else a text-style `TransportAbort` on the baseline | n/a | n/a |
| the 3 final-grade tests in `grader` (two faults then a pass; one fault then a fail; three faults) | (a) §10.1 regrade | now pass through the typed error | fail | pass |
| `reconcile::test_d1_the_recorded_numbers…`, `test_d1_the_offsets_are_recorded_but_not_required…` and `done_hook::test_the_recorded_d1_item…` | (a) §10.1 D1 | the fixture row carries `termination.last_step_start` = `msg_1f6b55ed0001AyZd9uTl8cwOWE`, the real last `step_start` `messageID` from `.fe-material/sgf-parsing/events.jsonl` (line 80); the 26th request_usage id is that id | fail | pass |
| `reconcile::test_d1_the_unpublished_shape_needs_the_recovered_message_to_be_the_streams_open_step` ×4 (missing / null / another step's id / not a string) (new) | (b) X9 | each refuses the `unpublished` shape; candidate 1 waived a missing id (by inspection) | pass (always refused) | pass |
| `chain::bare()` | X14 | sets the S27 chain state explicitly, since the chain no longer defaults any attribute | n/a | pass |

### 1.2 New tests, one scenario per adopted finding (`test_s27_fe_r1.py`, 53 tests)

| finding | tests | class | baseline | cand. 2 |
|---|---|---|---|---|
| X1 | the real `_parser()` of `run_tg1_probe`, `run_tg2_probe` and `run_oc_probe` accepts `interrupt`, keeps the other three kinds and refuses `bogus` (×3); the verifier, the run config and the driver share one kind list | (a), (c) | fail | pass |
| X2 | the accepted case with every anchor recorded (a trailing failed request opened before the SIGTERM, `/metrics` read 0): ok, `late_record.shape == open_step_at_signal`; the in-flight path is unchanged (b); 13 variants each remove one anchor and stay refused (no signal; no `signal_at`; no start or end offsets; one start too many; open step after the signal or before the n-th end; failed delta ≠ 1; failed line older than the SIGTERM; another or missing worker last error; another error text; failed line not last) | (a), (b) | accept case fails; the 13 refusals pass (they are refused there too) | pass |
| X4 | the sidecar the hook already sealed for this row: the leg continues (b); 6 variants each pause the leg: items path is a file, symlink to a valid sealed record, another row's, another attempt's, unsealed `{}`, a directory | (a), (b) | fail | pass |
| X7 | with a real driver whose probe child leads its own session, the child and its session are ours, the driver's own ambient session and an ambient bystander are not | (a) | fail | pass |
| X8 | a foreign record keeps the executable basename and `argc` only; no token, no path, no argument anywhere in the status | (a) | fail | pass |
| X10 | real processes through `ChainOps.owned_scan`: an environment-matched python is killed and verified, a path-only one is recorded by basename + argc and left alive, a bystander is untouched; a session member older than the probe's recorded start is not ours; one started after is killed; no recorded start proves nothing (not killed, `certain` False) | (a), (b) | fail | pass |
| X11 | an unreadable (`uids()` denied) probe-session member is never dropped, so the cleanup is uncertain; an unreadable foreign one is counted, not killed, not refused; one that exits discharges the obligation | (a), (b) | 2 fail, 1 pass | pass |
| X12 | v8 refuses an interrupt entry lacking its evidence: no row digest, malformed digest, nonzero rc, no rc, verifier not PASS, no verifier verdict (×6); the writer fails an interrupt whose row sha differs, and one whose probe rc is 1 | (a), (b) | fail | pass |
| X13 | a killed tracked process whose liveness lags and is then verified gone is not a survivor (certain); one really still alive stays a survivor and uncertain | (a), (b) | fail | pass |
| X14 | a Chain built without its state raises `AttributeError` for the S27 names and a misspelt one | (b) | pass | pass |
| X15 | a provably older unclaimed process with a denied cwd / cmdline / environ read is counted, not listed, not killed, not uncertain (×3) | (a) | fail | pass |
| X16 | the done hook's infrastructure error names the unevaluated checks (`ready_checks`, `reconciliation`, `engagement`; not `preconditions`); the chain's sidecar records `not_evaluated` exactly | (c) | fail | pass |
| X19 | a static guard: no test module other than the conftest wraps `ProcessGuard.__init__`; the init is at most one wrapper deep | (a), (b) | pass | pass | <!-- allow-shorthand: plain English -->

X5 is not a defect, so I wrote no test for it. X17 is checked by inspection: `fix-1.patch` removes the `session_id` parameter from `ProcessGuard.__init__` and `_run_item`, the leader path (`getsid(0) == getpid()`) is the only one left, and the ownership tests use it. For X6's tg1 Go typing (`structured_grade.parse_go`) I wrote no test, since the implementer's tests cover it; checked by inspection of the patch.

### 1.3 Unchanged since delivery 2

The v2 tests are unchanged except for the amendments above. The class (a) and (c) tests fail on the baseline and the class (b) tests pass on it; on the baseline copy none of my class (a) tests pass without a stated reason.

Baseline totals for the full set: **155 failed, 114 passed**. Candidate 2: **269 passed**.

## 2. Existing tests of the touched modules, on candidate 2

One invocation per family, run sequentially so timing does not interfere:

| family | result |
|---|---|
| `test_b2_*` | exit 0, no failures (2 skipped; total not recorded) |
| `test_c1*` | exit 0, no failures |
| `test_p371*` + `p371_baseline` | exit 0, no failures |
| `test_m6*` + `test_m7*` | exit 1, **5 failed** |
| `p586_frozen` + `s26_frozen` | exit 1, **1 failed** |
| `test_proc_guard*`, `test_p585*`, `test_g1*`, `test_c157*`, `test_c151*` | exit 0, no failures |

Failures, verbatim:

```
FAILED bench/tests/test_m64_arm_closure.py::test_the_tg1_carrier_and_plugins_the_arm_wraps_are_unedited_by_this_build
FAILED bench/tests/test_m76_b3_impl_golden_mtp.py::test_mtp_golden_is_meaningful
FAILED bench/tests/test_m76_b3_impl_golden_mtp.py::test_mtp_golden_component[leg_checks]
FAILED bench/tests/test_m76_b3_impl_golden_mtp.py::test_mtp_golden_committed_b8_and_signals_regenerate
FAILED bench/tests/test_m76_b4b1_fe_golden_tg1.py::test_b8_regenerates_byte_identical
  E  AssertionError: REFUSED: frozen stack_head_on f2b61127c55f0436b6c6c777bec5384ce004d62d does not resolve: git rev-parse failed
FAILED bench/tests/s26_frozen/test_s26_positives.py::test_fix_an_exception_message_never_carries_the_absolute_home_path
```

All six are the ones the implementer already reported as environmental: the frozen commit `f2b61127…` is absent from this clone, the canonical remote / `GATE_PUSHED_BASE` is absent, and pytest's tmp dir is under the home directory. I did not run the baseline copy on these families, because the brief asks for candidate 2 only, so "also failing on the baseline" is the implementer's statement, not mine.

X19 interference check: I ran the conftest-sensitive modules together with mine in one invocation (`test_c157`, `test_g1_round2`, `test_s27_fe_ownership`, `test_s27_fe_r1`, `test_p585…`, `test_proc_guard`): 206 passed. The two former broad-run-only tests (`test_p585…::test_the_scan_skips_a_process_it_cannot_construct_and_keeps_the_rest`, `test_proc_guard::test_real_rapid_fork_detach_chdir_is_attributed_or_diagnostic`) pass there. The whole-suite broad run itself I did not repeat.

## 3. Review of the fix

| finding | resolved? | evidence |
|---|---|---|
| X1 | yes | real-parser tests pass |
| X2 | yes | accept case plus 13 anchored refusals pass |
| X3 | yes | both staged scenarios pass |
| X4 | yes | the earlier (D) test now passes; 7 sidecar variants behave |
| X5 | not a defect | per the ledger |
| X6 | yes | typed error; agent output never a fault (tg1 Go by inspection) |
| X7 | yes | real-process test |
| X8 | yes | the guard's foreign record and the chain scan's `path_only` both keep the basename and `argc` |
| X9 | yes | missing, null, differing or non-string id refused |
| X10 | yes | one ownership rule shared by the guard and `owned_scan`; session bounded by the probe start |
| X11 | yes | claimed or counted, never dropped |
| X12 | yes | v8 requires rc 0, verifier PASS and the row digest |
| X13 | yes | lagging-exit test passes; a really-alive process is still a survivor |
| X14 | yes | the `__getattr__` and class defaults are gone |
| X15 | yes | counted for a denied cwd, cmdline or environ read |
| X16 | yes | the not-evaluated checks are named |
| X17 | yes | by inspection |
| X18 | partly checked | the frozen-test edits are listed in the fix report; every family I ran passes on candidate 2 apart from the environmental failures above, but I did not audit each edit against its spec clause |
| X19 | yes | the cause (a re-wrapped `__init__`) is removed; a static guard plus the combined run pass | <!-- allow-shorthand: plain English -->

Findings, all minor:

1. **`arm_runner.py` (`GradeWorker`, around the interim-fault path, X3), minor, traced by inspection only.** When an interim grade faults and `finish()` returns the fault, the capture's boundary was added to `gate.pending` at capture time but never discharged. After the client exits only the final boundary is discharged, so an earlier faulted boundary above `last_progress_boundary` could keep the stall rule from firing at the terminal decision. This affects only a stall flag on an item that also had an interim infrastructure fault; I did not reproduce it.
2. **`p426_reconcile._open_step_at_signal`, minor.** It compares the probe's `time.time()` (`signal_at`) with the worker's `timestamp_unix`, two wall clocks on one box. The risk is a clock step between them. It fails closed (a false refusal, not a false accept), and it matches the spec's "anchor on recorded evidence".
3. **`structured_grade.parse_go` (X6), minor.** `docker run` statuses 125/126/127 are typed as infrastructure faults, and the status is the container's, so a Go test binary that exits 126 or 127 through a wrapper could in principle be regraded three times and become a `grade_fault` DNF. I could not construct this, because `go test` itself exits 0, 1 or 2, so it is residual only.
4. **`ProcessGuard._claim_dropped` (X11), minor.** An unreadable session id on a dropped pid claims it (per §3.2 "as today"). On a leader probe this can turn a transient mid-exec pid into an uncertain, paused leg. It was already covered by the existing uncertain path; I note it as a possible false pause, not a hole.
5. **Heavier than the intent needs (carried over, not new).** The pause / hold machinery (`p426_holds`, `PAUSED`, `p426_wait_release`) and `owned_scan` as a second process-scanning implementation are the largest additions. X10 reduced the drift risk by sharing the claim helpers.

Deviations from the specification: the same two from delivery 2 (a denied read on a session-claimed process is killed and verified instead of made uncertain, X21 declined by the designer; the 4th harness DNF pauses with a designer release rather than a PAUSE-file hold), plus the §3.4 count of provably older unreadable processes, which X15 now matches.

Nothing was committed, pushed, reset or reverted; no environment variables or credentials were read or printed.

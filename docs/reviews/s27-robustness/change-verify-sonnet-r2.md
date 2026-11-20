I traced X2, X3, X4, X6, X8–X13 and X18 in the source. I did not trace X7, X14–X17 or X19 beyond the code I read and the implementer's report. I ran no tests (read-only review).

## Per-finding status

| id | status | basis |
|---|---|---|
| X1 | resolved | The inject kinds come from one shared tuple, per the report. I did not trace the three CLI parsers. |
| X2 | resolved, no hazard | `p426_reconcile.py:386-413`. The accepted case needs all of these:<br>- a delivered signal (`signal` and `signal_at` recorded);<br>- exactly one open step by END offsets, with `starts[n] <= signal`;<br>- `|S| == |C|+1`;<br>- one trailing STREAM_CLOSED failed line;<br>- a failed delta of 1;<br>- `failed_at >= signal_at`.<br>`signal_at` is taken just before the SIGTERM (`arm_runner.py:596`) and persisted only if the signal was delivered (`:602-605`). A worker failure before the signal is still refused. |
| X3 | resolved | `finish()` (`arm_runner.py:303-318`) now returns the interim infra fault. `_run_item` records it as `termination.interim_grade_fault` (`:777-779`). The final grade, with its own regrade (`final_grade`, `:976`), decides. A fault while the client is still running still goes through `check()` and reruns once. A grader thread that died mid-run is caught by `check()`, so the gate is never silently starved. |
| X4 | resolved | `accounting_sealed_for` (`p426_hooks.py:92-104`) requires an `lstat` regular file, a verified seal, and a matching slot, `rerun_index` and row sha. A symlink, a file-shadowed `items`, or an unreadable file returns False, so the leg pauses. |
| X5 | agree, not a defect | The stage resets at item start; the extra boundary reset is harmless. |
| X6 | resolved | Typing now happens at the source. `structured_grade.parse_go` types only docker's own rc 125/126/127. `tg2_grade.stage_failure` types only rc 125 without a timeout. A stderr pattern match alone still aborts untyped. |
| X7 | resolved | `bench_watch._ours` (`:507-523`) no longer claims the driver's own session. |
| X8 | resolved | `foreign_new` (`proc_guard.py:913-920`) and `path_only` (`chain_ops.py:1048`) keep only the scrubbed executable basename and `argc`. |
| X9 | resolved | `_late_record` (`:379`) requires `isinstance(last_id, str)` and `usage[-1][0] == last_id`. The probe records it at `arm_runner.py:850`. |
| X10 | resolved | The guard and the chain scan share `session_claim`, `env_claim`, `path_claim` and `hermetic_homes`. Session members must have started at or after the probe's recorded start (`chain_ops.py:1037`). A missing start disables the session claim and adds a problem, so the scan is uncertain and pauses. Unreadable processes are listed. |
| X11 | resolved | `_scan` reports pids it cannot construct in `denied`. `_claim_dropped` (`proc_guard.py:1304`) turns a tracked or session-claimed pid into a claimed obligation on `(pid, None)`; otherwise it counts the pid. Nothing is killed through this path. A `(pid, None)` obligation is resolved against the process table, not by a kill. |
| X12 | resolved under the stated trust model | v8 requires `interrupt_ok` (PASS, `verify_verdict` PASS, `probe_rc` 0, a 64-hex `row_sha256`). |
| X13 | resolved | The verification list is the killed set plus the audit's `alive`. The survivors are only the unverified ones. |
| X14–X17, X19 | resolved on the report and spot checks | Not traced end to end. |
| X18 | partly open | The 7 frozen conflicts await the test-writer's amendments. The full suite has not been run. |

## Findings

**P1: X12's v8 check cannot tell a real row from a made-up sha (minor, confirmed)**
- Location: `p426_freeze.py:220-224`.
- Problem: `interrupt_ok` accepts any 64-hex `row_sha256`. The row itself is verified only by the writer. This matches the settled trust model, but the interrupt is now the record's only cancellation proof.
- Scenario: a hand-edited or stale entry with a valid-looking sha passes v8. The record's own seal is the only other protection.
- Proposed change: if the interrupt's row is reachable from v8's inputs, compare its sha there. Otherwise leave it as is and state the limit in the spec.

**P2: a dropped fault on the unwind path (minor, confirmed)**
- Location: `arm_runner.py:958-959`.
- Problem: the `elif worker.thread.is_alive(): worker.finish()` call now silently discards a returned interim infra fault. It used to raise.
- Scenario: an exception is already unwinding and the grader thread has an infra fault. The fault is recorded nowhere, though cleanup is unaffected.
- Proposed change: store the return value in `termination["interim_grade_fault"]`, as at `:779`.

**P3: `argv` now holds only a basename (minor, confirmed)**
- Location: `proc_guard.py:915-919`.
- Problem: the key is still named `argv`, but a process that rewrites its argv[0] as a title could still put free text in the basename. `scrub` covers only known PII patterns.
- Scenario: an unrelated same-uid process with a title-style argv[0] lands in a public row, which is a small residual for X8.
- Proposed change: reduce `argv[0]` to its basename and also cap its length (for example 64 characters).

**P4: regrading is not yet shown clean (not a defect, a gate)**
- Seven frozen tests are pending amendment, and the whole suite has not run. The "no new failures" claim rests on the implementer's module families, which have environmental failures in this clone. I could not verify any of those from here.
- Proposed change: before round 3, run the whole suite on the baseline and on candidate 2 with the submodules and the canonical remote present, and compare the failure sets.

I found no new process kill outside the harness's ownership rules, no owned process left alive unrecorded, and no refusal lost at push or harvest. The one changed accept path, X2's, is anchored on recorded signal time and offsets, so the verdict does not depend on which event came first.
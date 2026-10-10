**Verdict: not ready for V3.** Reviewed HEAD `1c1626d`. Two live-run safety gaps remain: unrelated-process attribution (**P13**) and skipped cancellation after a kill-path error (**P14**). Repository unchanged; new fixtures are under `/tmp`.

| Prior finding | Status | Evidence |
|---|---|---|
| P1 — kill ownership | **PARTIAL** | Path-only processes are no longer killed; age and protected-PID checks added. Ancestry attribution still admits unrelated processes: **P13**. |
| P2 — interrupted acquisition | **FIXED** | Signals deferred across spawn/registration; failed registration kills through the owned `Popen` handle. [proc_guard.py:349]($STACK_REPO/benchmark/bench/proc_guard.py:349). SIGTERM/SIGINT and runner-cleanup tests pass. |
| P3 — kill→cancel→export | **PARTIAL** | Watchdog termination now cancels before drain/export; lifecycle tests pass. A kill-path exception still skips cancellation: **P14**. |
| P4 — terminal reconciliation | **FIXED** | Normal completion requires a terminal finish; killed active message must match the trailing assistant. [token_turn_gate.py:420]($STACK_REPO/benchmark/bench/token_turn_gate.py:420). Original counterexamples pass. |
| P5 — Go `TestMain` | **FIXED** | Lexer ignores comments/literals and handles commented declarations. [structured_grade.py:98]($STACK_REPO/benchmark/bench/structured_grade.py:98). Existing-file and false-positive tests pass. |
| P6 — malformed tools | **FIXED** | Terminal state and field types validated before updating K. [token_turn_gate.py:222]($STACK_REPO/benchmark/bench/token_turn_gate.py:222). Malformed-state tests pass. |
| P7 — scoring identity | **FIXED** | Scoring dependencies included in code hash; clamp mutation changes identity and refuses append. [tg1_runner.py:249]($STACK_REPO/benchmark/bench/tg1_runner.py:249), [mutation test]($STACK_REPO/benchmark/bench/tests/test_m62_v5a_identity.py:26). |
| P9 — abbreviated flags | **FIXED** | tg1 reparses with abbreviation disabled; twelve abbreviation cases pass. [run_opencode_probe_v2.py:867]($STACK_REPO/benchmark/run_opencode_probe_v2.py:867). |
| P10 — frozen manifest | **FIXED** | Existing destination requires `--refreeze`; replacement is atomic. Refusal and interrupted-replacement tests pass. [build_replay_manifest.py:24]($STACK_REPO/benchmark/m62/build_replay_manifest.py:24). |
| P11 — weak tests | **PARTIAL** | Acquisition, cancellation ordering, copied-manifest mismatch and exact memory-limit assertions added. Container OOM observation remains mocked as unconditional `True`: [test_structured_grade.py:220]($STACK_REPO/benchmark/bench/tests/test_structured_grade.py:220). New ownership/error counterexamples below remain uncovered. |

**P13 — BLOCKER: a stale parent identity can authorize killing an unrelated process.**

At [proc_guard.py:274]($STACK_REPO/benchmark/bench/proc_guard.py:274), `ppid()` raising `NoSuchProcess` merely skips that entry; it does **not** remove the stale parent from `alive`. Another process can then inherit ownership through that stale entry at line 278.

Constructed scenario:

1. A previously tracked item shell exits and is reaped.
2. Its PID is reused by an unrelated operator process, which spawns a child.
3. Installed psutil 7.2.2 can retain the old `Process` object and cached creation time in `process_iter()`. Its `ppid()` rejects the reused identity.
4. The guard nevertheless uses that old entry as the new child’s parent, records the unrelated child’s **correct** PID/create-time pair, and kills it.

The [safety fixture](/tmp/m62-head-review-hoxkz3ht/test_safety_regressions.py:6) fails: unrelated PID `99203` becomes role `model` and receives the mocked kill. Target create-time validation cannot repair an incorrect ownership decision.

**Required fix:** validate parent identity when authorizing each ancestry edge; discard invalid identities from ancestry lookup. Add the stale-cache counterexample.

**P14 — MAJOR: the new scan inside `kill_role()` can suppress worker cancellation after killing the client.**

[proc_guard.py:389]($STACK_REPO/benchmark/bench/proc_guard.py:389) calls `tick()` inside `try`, then signals tracked processes in `finally`. Thus a scan error can propagate **after** the client was killed.

[terminate_client()]($STACK_REPO/benchmark/bench/tg1_runner.py:355) does not protect subsequent model cleanup and cancellation from that exception. Its outer cleanup retries the same failing path.

Two fixtures establish the chain:

- [Actual `kill_role()` fixture](/tmp/m62-head-review-hoxkz3ht/test_safety_regressions.py:35): injected `AccessDenied` propagates after the client is killed.
- [Runner fixture](/tmp/m62-head-review-hoxkz3ht/test_safety_regressions.py:47): observed `kill-client → kill-client → kill-grader → cleanup`, with **no cancellation check**.

This is a termination-path regression introduced by the added scan. Export is prevented, but the worker can remain busy when the probe exits.

**Required fix:** attempt remaining owned-process cleanup and worker cancellation even when a kill operation raises, then propagate the failure.

**P15 — Complete signal/kill inventory.**

| Path | Target ownership guarantee and limitation |
|---|---|
| [`_mem_kill`, line 320]($STACK_REPO/benchmark/bench/proc_guard.py:320), invoked by per-process and aggregate limits | Tracked PID/create-time, age check, explicit exclusions. Roots come from registered spawns; descendants inherit ancestry. **P13 breaks that inheritance guarantee.** |
| [`kill_role`, line 399]($STACK_REPO/benchmark/bench/proc_guard.py:399) | Fresh PID lookup, matching creation time, live status and exclusions. Same ancestry weakness; its preceding `tick()` can also kill through memory limits regardless of requested role. |
| [`cleanup` sweep, line 475]($STACK_REPO/benchmark/bench/proc_guard.py:475) | Only tracked tuples surviving age/exclusion checks are killed. Path-only matches abort without signalling. Incorrectly tracked P13 victims remain eligible. |
| [`spawn` fallback, line 365]($STACK_REPO/benchmark/bench/proc_guard.py:365) and [`cleanup` acquisition fallback, line 458]($STACK_REPO/benchmark/bench/proc_guard.py:458) | Direct `Popen` handles returned by this guard’s spawn. Ownership rests on the child handle, not ancestry or pathname; registration may not yet exist. |
| [`run_grader` timeout, line 383]($STACK_REPO/benchmark/bench/proc_guard.py:383) | Delegates to `kill_role("grader")`; inherits its guarantees and weaknesses. |
| [`remove_container`, line 424]($STACK_REPO/benchmark/bench/proc_guard.py:424) | `docker rm -f` targets a generated, registered run/item/sequence name. Ownership is name-based, not container-ID-based. It does not signal Docker Desktop itself. |
| `subprocess.run` at lines 414, 423 and 426 | Timeout/exception handling can kill the newly spawned Docker **CLI child**, through its own `Popen` handle. |
| [`defer_signals`, line 173]($STACK_REPO/benchmark/bench/proc_guard.py:173) | Re-raises a deferred signal to the **probe itself** when the previous handler was `SIG_DFL`; intentional signal delivery, not item cleanup. |
| `tg1_runner.py` | No raw signal syscall. Lines **355–356** kill client/model roles; **561** kills graders; **568** invokes full cleanup. Discovery context exits at **680/768**, export timeout at **464**, and structured grading also delegate to the guard paths above. |

Probe/ancestor PIDs, recorded router/worker PIDs, and processes older than guard start are excluded from tracked-process kills. There is **no blanket other-session exclusion** for tracked processes—legitimate detached descendants remain killable. Consequently, P13 can reach a new unrelated process in another terminal session. I did not reproduce a signal to the recorded router/worker or pre-existing Docker Desktop processes.

**P16 — Verification.**

- M62 suites: **218 passed**, including pinned-client mock-HTTP integration; no inference or Docker runs.
- Original adversarial file, unchanged: **6 passed, 1 failed** because its fake process lacks `wait()`.
- [Compatibility copy](/tmp/m62-head-review-hoxkz3ht/test_original_compatible.py), adding only fake `wait`/`poll`: **7 passed**.
- New safety fixtures: **2 failed, 1 passed**, reproducing P13/P14 with mocked signals.
- Requested replay: **exit 0; all eight criteria PASS**, including all 374 valid historical passes remaining unstopped.
- No gate/accounting regression observed in those checks. **Hold V3 for P13 and P14.**
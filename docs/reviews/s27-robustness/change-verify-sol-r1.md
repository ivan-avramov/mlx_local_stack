P1 — Interrupt positive cannot run end to end

- Location: `benchmark/run_tg1_probe.py:69,104`; `benchmark/run_tg2_probe.py:71,106`; `benchmark/run_oc_probe.py:71,114`; caller at `benchmark/bench/p426_wave2.py:1909-1925`
- Severity: blocker
- Evidence: confirmed — source trace
- Resolution: not resolved.
- Problem: all CLI parsers reject `interrupt`, although the positives driver invokes `--tg2-inject interrupt`.
- Failure scenario: `argparse` exits before creating a row; both permitted attempts become transport aborts, so the mandatory positives record cannot pass and the chain cannot proceed.
- Tests miss: they call internal seams or doubles and never execute the real parser/subprocess chain.
- Proposed change: use the shared `ALL_INJECT_KINDS` in both normal and identity parsers and test the actual subprocess entry point.

P2 — Kill reconciliation still depends on metrics-versus-request ordering

- Location: `benchmark/bench/arm_runner.py:559-605`; `benchmark/bench/p426_reconcile.py:402-428`
- Severity: major
- Evidence: confirmed — source trace
- Resolution: not resolved.
- Problem: the completed count, `/metrics` sample, and SIGTERM are separate events. A new request can start after metrics reports zero but before SIGTERM. The serialized log proves that request existed, yet reconciliation requires the earlier metrics sample to say it was in flight.
- Failure scenario: `|C| == expected`, followed by one terminal `STREAM_CLOSED` failure and `|S| == |C|+1`; `in_flight_at_kill == 0`. This becomes an off-table integrity failure and invalidates the leg.
- Tests miss: no test schedules a request start specifically between the metrics read and signal.
- Proposed change: accept the terminal serialized worker-log shape as sufficient in-flight evidence; retain metrics and signal ordering diagnostically.

P3 — A post-generation interim-grader fault regenerates the item

- Location: `benchmark/bench/arm_runner.py:292-313,689-769`; routing at `benchmark/bench/chain_core.py:2871-2930`
- Severity: major
- Evidence: confirmed — source trace
- Resolution: not resolved. Final-grade retries correctly retain one snapshot, but this boundary does not.
- Problem: `GradeWorker.check()` always labels infrastructure failure as `stage="generation"`. After the client exits, `worker.finish()` may first observe a worker failure that occurred after generation finished. The chain consequently treats it as pre-outcome and regenerates.
- Failure scenario: the client finishes between the loop’s last `worker.check()` and `worker.finish()`; an outstanding interim grade then fails. The completed generation is discarded and rerun.
- Tests miss: interim failure is injected while the client is visibly still generating.
- Proposed change: close or cancel interim grading at client completion. Faults first observed afterward must follow an outcome-preserving final-grade/post-outcome path, never regeneration.

P4 — Accounting sidecar persistence fails open

- Location: `benchmark/bench/chain_core.py:3263-3273`; `benchmark/bench/p426_hooks.py:54-77`
- Severity: major
- Evidence: confirmed — source trace and the remaining frozen-test failure
- Resolution: not resolved.
- Problem: `p426_write_accounting()` treats every `FileExistsError` as proof that the hook already sealed the sidecar. The exception can instead come from an ancestor-path collision, and an existing sidecar is never validated.
- Failure scenario: `items` is a regular file. Parent creation raises `FileExistsError`; the chain returns success and continues without the required durable post-outcome fault record.
- Proposed change: succeed only if the exact sidecar is a regular, non-symlink, valid sealed document matching the current slot, row, item record, and checks. Otherwise PAUSE.

P5 — Owned processes can be skipped before ownership classification

- Location: `benchmark/bench/proc_guard.py:73-91,497-515,1292-1350`; duplicated in `benchmark/bench/chain_ops.py:979-1019`
- Severity: major
- Evidence: confirmed — source trace
- Resolution: partially resolved. No path that kills a readable path-only or foreign process was found, but an owned process can survive unrecorded.
- Problem: a process unseen in the previous tick is discarded when `psutil.Process(pid)` cannot be constructed; processes are also discarded when `uids()` is denied. These reads happen before session, tracked-PID, or ancestry ownership is considered. The direct audit covers only already-tracked identities.
- Failure scenario: a client spawns a same-session descendant just before cleanup and its parent exits. A transient macOS `SystemError`/`AccessDenied` during construction or `uids()` causes the only cleanup scan to omit it; cleanup reports certain while it remains alive.
- Tests miss: denied reads are exercised after a process object has already entered the listing, not at construction or UID filtering.
- Proposed change: retain unreadable PID placeholders and evaluate tracked/session claims first using PID and `getsid`. Any unreadable claimed identity must remain an uncertain obligation. Reuse this logic in the chain’s second scan.

P6 — A positives record can pass without validating interrupt proof

- Location: `benchmark/bench/p426_wave2.py:426-451`; `benchmark/bench/p426_freeze.py:220-228,942-980`
- Severity: major
- Evidence: confirmed — source trace
- Resolution: not resolved.
- Problem: downstream acceptance requires only `{kind: "interrupt", verdict: "PASS"}`. It does not bind `probe_rc`, verifier verdict/result, row hash, or causal in-flight evidence. The writer also skips row verification if the row disappears after `inject_verify`.
- Failure scenario: a sealed record containing a declared interrupt PASS but no valid row or cancellation evidence passes `positives_problems()` and can freeze into v8.
- Tests miss: they validate verdict shape and even permit a synthetic PASS entry without proof.
- Proposed change: add and validate self-contained `interrupt_evidence`, including verifier PASS, rc 0, row/evidence hashes, client kill, in-flight observation, interrupted trailing shape, and cancellation consistency.

P7 — Watcher ownership hides unrelated same-session CPU load

- Location: `benchmark/m1/bench_watch.py:507-566`; chain launch at `benchmark/bench/p426_wave2.py:1759-1774`
- Severity: major
- Evidence: confirmed — source trace
- Resolution: not resolved.
- Problem: `BoxSampler._ours()` adds the session ID of the driver and every descendant, then labels every process with any such SID as `ours`. The chain is not launched in a new session, so its SID is normally the ambient shell session, not an ownership boundary.
- Failure scenario: a detached/background chain and an unrelated package-manager or endpoint-agent command launched from the same shell session run concurrently. The unrelated process exceeds 150% CPU for two ticks but is classified `ours`; no ALERT is emitted and speed evidence remains valid.
- Tests miss: `box_alerts()` receives hand-labelled rows; no test exercises `BoxSampler` against real session topology.
- Proposed change: classify exact driver descendants as owned and add only sessions led by identified probe descendants (`sid == pid`). Do not claim the driver’s ambient session. This is also simpler than broad session-set propagation while retaining escaped-probe coverage.

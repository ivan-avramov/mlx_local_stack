P1

- Location: `docs/specs/s27-harness-robustness.md` §5.1–§5.3; `p426_hooks.P426Hooks.after_attempt`; `p426_reconcile._reconcile`
- Severity: major
- Evidence: confirmed
- Problem: “A reconciliation failure … that is not an integrity fault” is too broad, while §5.3 does not classify genuine accounting failures as integrity faults. Consequently failures of `worker_deltas`, `session_backend`, positional pairing, or request counts become retryable harness faults. Acceptance merely says a genuine mismatch remains “a fault,” not that it still invalidates.
- Concrete failure scenario: the worker records an extra completion not represented by client usage. The first attempt is discarded, the retry reconciles, and the leg passes, hiding an unaccounted generation that can affect cache state and token accounting.
- Proposed change: define a closed harness-fault allowlist. Count, pairing, session/backend, worker-delta, receipt-chain, and unexplained request mismatches must remain integrity/systemic invalidations. The genuine-mismatch acceptance test must assert leg `INVALID`, not retry/DNF.

P2

- Location: spec §5.1–§5.2 versus §3.2–§3.4; `chain_core.require_certain_cleanup`, `p426_dnf_eligible`, `record_incident`
- Severity: blocker
- Evidence: confirmed
- Problem: the spec classifies owned-cleanup `uncertain` as a harness fault and then directs an immediate retry or DNF-and-continue. Existing call paths require certain cleanup before every retry precisely because an unverified owned process may still mutate files or consume resources.
- Concrete failure scenario: a client child survives cleanup with unreadable identity. The same slot reruns while that child continues writing under the run roots; after a second fault the leg records a DNF and proceeds with later items under contamination.
- Proposed change: an uncertain cleanup may record a harness fault, but no retry, DNF continuation, or HOLD release may occur until a subsequent cleanup proves certainty. If certainty cannot be recovered, pause the preserved leg for intervention; never continue.

P3

- Location: spec §5.1–§5.2; driver assumption 3; `chain_core.run_p426_leg`; `chain_rows.load_slots`
- Severity: major
- Evidence: confirmed
- Problem: same-rule, same-seed retries are not outcome-neutral. Reconciliation faults happen after a model outcome exists and are especially reachable on stall/loop kill paths. Discarding that attempt and scoring a fresh agent run selectively gives another draw to outcomes and arms that exercise those paths.
- Concrete failure scenario: arm A loops and encounters a kill-boundary reconciliation race; its retry completes successfully. Arm B produces an ordinary scored failure and receives no retry. Arm A is credited with the second outcome despite its first model outcome being a strict-fail loop.
- Proposed change: restrict single-arm retries to faults occurring before any model outcome is classifiable. For post-outcome faults, use a pre-registered paired treatment—such as rerunning the corresponding slot for both arms—or escalate this settled ruling to the operator.

P4

- Location: spec §4.1–§4.2; `arm_runner.terminate_client`; `token_turn_gate.EventStream`; `p426_reconcile._reconcile`
- Severity: major
- Evidence: confirmed
- Problem: `signal_offset` does not close the whole race. `requests_at_kill` is captured before the metrics read and SIGTERM, so a completion can be recorded between that snapshot and the signal with an offset below `signal_offset`. Also, existing event offsets identify the line’s first byte, so a `step_finish` write begun before SIGTERM but completed afterward is rejected.
- Concrete failure scenario: the gate snapshots `expected=25`; request 26 completes and its `step_finish` is written while the metrics call runs; SIGTERM follows. Counts are the benign `26/26/25`, but the finish offset is before the signal, so the proposed late-record case still invalidates the leg.
- Proposed change: record a decision offset alongside `requests_at_kill`, plus each event’s end offset. Accept the extra completion only when its complete line crosses or follows that decision boundary; retain `signal_offset` to record whether it was before or after SIGTERM.

P5

- Location: spec §3.3–§3.4 and §8.3; `arm_runner._run_item`; `p426_wave2.classify_leg`; watcher `_chain_view`
- Severity: major
- Evidence: confirmed
- Problem: the spec adds `foreign_new` to cleanup status but does not require propagation on successful items. On the current success path, cleanup status remains in `ctx`; only abort/hook-stop manifests persist it. Rows expose `orphans_unattributed` separately, but no equivalent path is specified for `foreign_new`.
- Concrete failure scenario: `helpd` starts during an otherwise successful item and remains alive at cleanup. Cleanup is certain and the invocation validates, but its `foreign_new` observation disappears, so neither classification nor harvest can report it.
- Proposed change: require every row or immutable per-item cleanup record to carry `foreign_new`; aggregate it into chain/leg records and harvest it. Update the watcher and tier classifier to consume that persisted source.

P6

- Location: spec §8.1 and §8.3; `benchmark/m1/bench_watch.py` P426 watcher
- Severity: major
- Evidence: confirmed
- Problem: the proposed top-five record contains only process name and CPU percentage, but the threshold applies specifically to a “non-harness” process. Names cannot distinguish owned router, worker, probe, grader, or client processes from foreign processes, especially across their separate sessions.
- Concrete failure scenario: an owned grader or worker exceeds 150% CPU on two ticks and is classified as foreign, producing an `ALERT` and making an otherwise valid leg speed-invalid on a normal run.
- Proposed change: record PID, SID, start identity, and scrubbed argv; classify ownership from the chain’s router/worker/probe identities and descendant/root attribution. Unclassifiable processes should be recorded as unknown, not automatically treated as foreign.

P7

- Location: spec §5.2 and §8.2; `chain_core.pump_barrier`/`run_p426_leg`; `p426_wave2.Sequencer.supervise`
- Severity: major
- Evidence: confirmed
- Problem: “the 4th → the sequencer pauses the leg” has no race-free call path. The chain alone controls `.continue` and launches the next invocation immediately; the sequencer only polls every 30 seconds and intentionally never signals the chain.
- Concrete failure scenario: the fourth harness-fault DNF is persisted, the chain sends `.continue`, and one or more subsequent items start before the sequencer notices and creates or reacts to `HOLD`.
- Proposed change: enforce the threshold synchronously in the chain at the item barrier, before `.continue` or the next `.ready`. Persist the fourth DNF and hold episode atomically; let the sequencer only notify and record. Clarify whether the threshold is three permitted DNFs plus a paused fourth, and how resume avoids immediately re-pausing.

**Not cleared.** Reviewed HEAD `84d6e5a8` and build commit `9e65137c`. **548 tests passed**, `git diff --check` passed, and the working tree remains clean. Read-only counterexamples reproduced the failures below.

1. **Q12 — blocker — teardown still adopts unowned processes.** [chain_ops.py:284](<repo>/benchmark/bench/chain_ops.py:284) records whichever process acquires :8000 after spawn, **before** verifying it. It never proves ancestry from the spawned process. A foreign listener appearing between preflight and startup therefore becomes a teardown target even when startup refuses its environment. My mocked counterexample refused the foreign listener, then signalled it with both SIGTERM and SIGKILL. Additionally, [stop_stack:409](<repo>/benchmark/bench/chain_ops.py:409) unloads by model name without checking `worker_started` or current router ownership.
   
   **Change:** acquire router ownership through the spawned handle and verified descendant identities; retain foreign listeners only as diagnostics. Before HTTP unload, verify the recorded router and worker identities. Test foreign acquisition after spawn and router/worker replacement before teardown.

2. **Q13 — blocker — completed edits still do not prove creation ownership.** [proc_guard.py:862](<repo>/benchmark/bench/proc_guard.py:862) treats a completed write/edit as proof of creation. Another process can create a file after the pre-item listing, then the model can successfully edit it. That file passes every check and is deleted. My mocked filesystem counterexample returned `cleaned=["/tmp/theirs"]` and called unlink. The after-listing also records identity too late to detect replacement between tool completion and that listing; nested file identities are first acquired during cleanup.
   
   **Change:** keep external `/tmp` paths diagnostic unless creation ownership and the created inode were actually recorded. A completed edit, absent-before name, uid and timestamp are insufficient. Test successful edits of unrelated-created files and replacement before the after-listing. Removing recursive deletion fixes part of Q2, but does not answer P1.

3. **Q14 — blocker — the pinning fix prevents the default real pilot from completing.** [run_tg1_chain.py:405](<repo>/benchmark/chains/c147/run_tg1_chain.py:405) requires every pinned field to be truthy, including `agent_system_sha256`. The real carrier correctly sets this field to `None` when no overlay is supplied ([run_opencode_probe_v2.py:236](<repo>/benchmark/run_opencode_probe_v2.py:236)); the runner supplies no overlay ([build_cmd:104](<repo>/benchmark/chains/c147/run_tg1_chain.py:104)). Passing that real selection through pinning produced `first complete leg lacks pinned identity fields: ['agent_system_sha256']`. The fake manifest masks this with an invented non-null hash ([fake_probe.py:55](<repo>/benchmark/chains/c147/fake_probe.py:55)).
   
   **Change:** distinguish absent keys from explicitly null optional identities. Pin and compare null as a value. Make the fake default match the real carrier, and test real default-carrier pilot→full pinning.

4. **Q15 — blocker — report validation still admits false clearance.** [inject_verify.py:97](<repo>/benchmark/m62/inject_verify.py:97) accepts absent or empty `grade_reports`; removing every report from a loop fixture still returned `PASS` with `cancellation_proven`. [validate_leg:616](<repo>/benchmark/bench/chain_ops.py:616) now requires a nonempty final artifact, but does not validate the receipt schema or permitted terminal outcome. A final receipt with `outcome="infrastructure"`, `seq=-1`, no boundary and one unrelated hashed artifact returned `[]`.
   
   **Change:** validate report records in both verifiers: typed boundary/sequence/final fields, sequence uniqueness, a valid final receipt, permitted outcomes and required language-specific artifacts. Preserve the explicit tampered exception. Add missing-report, malformed-receipt and infrastructure-final mutation tests.

5. **Q16 — should-fix — transport tolerance still exceeds B1’s causal exception.** [token_turn_gate.py:391](<repo>/benchmark/bench/token_turn_gate.py:391) accepts arbitrary text after the shortened prefix `Transport: Unable to connect.` My counterexample ending in `upstream model failed; retrying` reconciled successfully. Moreover, [tg1_runner.py:512](<repo>/benchmark/bench/tg1_runner.py:512) sets `signal_index` before fetching metrics and before sending the signal. It measures ingestion order, so already-written but unread events—or errors arriving during the metrics call—can be classified as post-signal.
   
   **Change:** freeze the complete allowed messages and establish the cutoff at actual signalling using the raw event-file position. Reject pre-signal bytes even if ingested later. Test both unknown suffixes and a transport error emitted during the pre-kill metrics call.

6. **Q17 — blocker — denied inspection can still certify an owned survivor as gone.** [proc_guard.py:263](<repo>/benchmark/bench/proc_guard.py:263) silently excludes processes when `uids()` or `status()` raises `AccessDenied`. Cleanup’s new uncertainty handling never sees them. [verify_gone:488](<repo>/benchmark/bench/proc_guard.py:488) also converts denied inspection into successful disappearance. My tracked-process counterexample remained alive while cleanup returned `survivors=[]`, `uncertain=False`, and `verify_gone=True`.
   
   **Change:** audit every tracked identity independently of the filtered process scan. Denied identity/liveness inspection must mean unknown, blocking clearance and restart. Test denial at `uids`, `status`, `create_time` and final verification, alongside the existing cwd/cmdline cases.

7. **Q18 — should-fix — cancellation remains inferred from aggregate counters.** [inject_verify.py:135](<repo>/benchmark/m62/inject_verify.py:135) correctly rejects successful natural completion, but unchanged `requests_completed` plus busy→idle also describes an independently failed request. That summary received `cancellation_proven` in my counterexample. There is still no request/session-correlated cancellation evidence.
   
   **Change:** require a correlated worker cancellation receipt or log event. Until available, label this observation as cancellation-consistent rather than proven and retain `not_observed:cancellation` for clearance.

Q1–Q11 status against the current code:

| ID | Status | Evidence |
|---|---|---|
| Q1 | **Partial** | Name-based teardown removed, but listener acquisition and HTTP unload remain unowned: [chain_ops.py:284](<repo>/benchmark/bench/chain_ops.py:284), [409](<repo>/benchmark/bench/chain_ops.py:409). Q12. |
| Q2 | **Partial** | Completed status required and recursive deletion removed; creation ownership remains unproven: [proc_guard.py:806](<repo>/benchmark/bench/proc_guard.py:806), [862](<repo>/benchmark/bench/proc_guard.py:862). Q13. |
| Q3 | **Answered** | Probe writes the top-level receipt and runner consumes it: [tg1_runner.py:1222](<repo>/benchmark/bench/tg1_runner.py:1222), [run_tg1_chain.py:158](<repo>/benchmark/chains/c147/run_tg1_chain.py:158). Real-manifest test: [test_c147_chain_runner.py:922](<repo>/benchmark/bench/tests/test_c147_chain_runner.py:922). |
| Q4 | **Partial** | Row scaffold/model/overlay checks added: [chain_ops.py:597](<repo>/benchmark/bench/chain_ops.py:597). Report gaps remain; mandatory identity handling introduced Q14. Q14/Q15. |
| Q5 | **Answered** | Unreadable latest attempt retained; missing requested kind fails: [inject_verify.py:297](<repo>/benchmark/m62/inject_verify.py:297), [317](<repo>/benchmark/m62/inject_verify.py:317). |
| Q6 | **Partial** | Successful completion-counter rise is rejected; correlation remains absent: [inject_verify.py:119](<repo>/benchmark/m62/inject_verify.py:119). Q18. |
| Q7 | **Answered** | Cancellation rechecked after terminal cleanup, before returning the item for row commitment: [tg1_runner.py:383](<repo>/benchmark/bench/tg1_runner.py:383). |
| Q8 | **Partial** | One occurrence per shape and ingestion-index bounds added: [token_turn_gate.py:396](<repo>/benchmark/bench/token_turn_gate.py:396). Message and actual-signal bounds remain defective. Q16. |
| Q9 | **Partial** | Cleanup catches denied inspection inside its sweep: [proc_guard.py:597](<repo>/benchmark/bench/proc_guard.py:597). Earlier filtering and disappearance verification still hide owned survivors. Q17. |
| Q10 | **Answered** | Typed tampered final receipt emitted and explicitly accepted: [tg1_runner.py:764](<repo>/benchmark/bench/tg1_runner.py:764), [chain_ops.py:622](<repo>/benchmark/bench/chain_ops.py:622). |
| Q11 | **Answered** | Escalation checks heartbeat changes, events, rows, worker identity and metrics; drift refuses signalling: [run_tg1_chain.py:535](<repo>/benchmark/chains/c147/run_tg1_chain.py:535). Teardown ownership is separately Q12. |

Re-verification of the design findings previously partial or unanswered:

| ID | Status now | Code evidence |
|---|---|---|
| P1 | **Partial** | Failed-edit and recursive-delete defects fixed; creation ownership still absent: [proc_guard.py:862](<repo>/benchmark/bench/proc_guard.py:862). Q13. |
| P3 | **Partial** | Shared cleanup receipt implemented, but teardown ownership and survivor certainty remain defective: [chain_ops.py:402](<repo>/benchmark/bench/chain_ops.py:402), [proc_guard.py:263](<repo>/benchmark/bench/proc_guard.py:263). Q12/Q17. |
| P4 | **Answered** | Terminal-phase cancellation, retained evidence and computed deadline: [tg1_runner.py:378](<repo>/benchmark/bench/tg1_runner.py:378), [chain_ops.py:459](<repo>/benchmark/bench/chain_ops.py:459). |
| P10 | **Partial** | Descendant and kill evidence checked, but cancellation remains uncorrelated: [inject_verify.py:141](<repo>/benchmark/m62/inject_verify.py:141). Q18. |
| P11 | **Partial** | Common identities and row provenance checked; optional-identity regression and report validation gaps remain: [run_tg1_chain.py:397](<repo>/benchmark/chains/c147/run_tg1_chain.py:397), [chain_ops.py:616](<repo>/benchmark/bench/chain_ops.py:616). Q14/Q15. |
| P12 | **Partial** | Launch-time retention and exception indexing implemented: [structured_grade.py:304](<repo>/benchmark/bench/structured_grade.py:304), [370](<repo>/benchmark/bench/structured_grade.py:370). Verifier acceptance remains weak. Q15. |
| P13 | **Partial** | Real probe cancellation and receipt tests exist: [test_c147_cancel.py:318](<repo>/benchmark/bench/tests/test_c147_cancel.py:318). Fake default identity still conceals a real contract failure: [fake_probe.py:55](<repo>/benchmark/chains/c147/fake_probe.py:55). Q14. |
| P15 | **Partial** | Latest-attempt aggregation fixed; authoritative verifier still accepts absent reports: [inject_verify.py:97](<repo>/benchmark/m62/inject_verify.py:97), [297](<repo>/benchmark/m62/inject_verify.py:297). Q15. |
| P17 | **Partial** | Barrier and escalation checks implemented: [run_tg1_chain.py:474](<repo>/benchmark/chains/c147/run_tg1_chain.py:474), [535](<repo>/benchmark/chains/c147/run_tg1_chain.py:535). Ownership/cleanup clearance remains unsafe. Q12/Q17. |
| P19 | **Answered** | Descriptor seeds, mandatory overlay hash and aborted-resume refusal: [chain_ops.py:560](<repo>/benchmark/bench/chain_ops.py:560), [601](<repo>/benchmark/bench/chain_ops.py:601), [tg1_runner.py:1072](<repo>/benchmark/bench/tg1_runner.py:1072). |

P2, P5–P9, P14, P16, P18 and P20–P22 retain their round-1 **answered** status; they were not re-reviewed beyond regression checks.

The §9 build findings:

- **B1:** SIGTERM-first, 15-second grace, survivor SIGKILL and model-role SIGKILL are implemented at [tg1_runner.py:533](<repo>/benchmark/bench/tg1_runner.py:533). Both transport shapes are recognized. **Q16 still weakens §3a beyond the stated own-stop exception.**
- **B1b:** `interrupted_charged` validates and charges trailing aborted usage once, including terminal checks: [token_turn_gate.py:464](<repo>/benchmark/bench/token_turn_gate.py:464), [499](<repo>/benchmark/bench/token_turn_gate.py:499). No additional weakening found.
- **B2:** Inject alloc uses **512 MiB** and the **1 GiB** command: [tg1_runner.py:42](<repo>/benchmark/bench/tg1_runner.py:42), [50](<repo>/benchmark/bench/tg1_runner.py:50). Campaign constants remain unchanged.
- **B3:** The real-client test verifies the frozen killed-command fixture’s SHA and normalized content: [test_c147_inject.py:358](<repo>/benchmark/bench/tests/test_c147_inject.py:358). The verifier accepts the registered error/signal/nonzero-exit alternatives at [inject_verify.py:107](<repo>/benchmark/m62/inject_verify.py:107). No §3a weakening found.

The campaign policy hash remains `ba86ba16…`; its pin test passed. Explicit inject-labelled rows are now rejected by campaign leg validation. I found no personal home paths or PII in the reviewed committed additions. The new findings expose missing acceptance tests despite the passing suites. Live inject clearance and the real pilot remain pending.

not cleared
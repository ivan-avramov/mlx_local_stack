Reviewed implementation `20e41354`; current HEAD `e20b0fc8` adds only handoff documentation. **607 tests passed**, `git diff --check` passed, and the working tree remains clean. Counterexamples below used mocked effects; no source files were written.

1. **Q19 — blocker — HTTP unload still lacks endpoint ownership.**  
   [chain_ops.py:377](<repo>/benchmark/bench/chain_ops.py:377) sends unload without ownership checks. [stop_stack:446](<repo>/benchmark/bench/chain_ops.py:446) checks recorded process liveness, but does not establish that the recorded router still owns :8000. Additionally, [run_inject.py:132](<repo>/benchmark/chains/c147/run_inject.py:132) directly unloads before guarded teardown.

   A counterexample with the recorded router/worker still alive but foreign PID 999 owning :8000 sent `/v1/models/unload` to that foreign endpoint. **Change:** centralize checks in `unload`: require the sole current listener to match the recorded router identity and the current worker to match `worker_started`; refuse otherwise. Cover normal block transitions, final unload and exception cleanup.

2. **Q20 — blocker — directory deletion bypasses Q13’s content-match decision.**  
   [proc_guard.py:854](<repo>/benchmark/bench/proc_guard.py:854) immediately removes an empty directory; the content-hash check exists only in the regular-file branch at [866](<repo>/benchmark/bench/proc_guard.py:866).

   A completed-write candidate whose file was replaced by an unrelated empty directory before the after-listing returned `cleaned=["/tmp/replacement"]` and invoked `rmdir`, without checking written content. This exceeds the accepted B8 decision. **Change:** require a write candidate itself to remain a regular file with matching content; retain replacement directories diagnostically. Add the replacement-before-after-listing test.

3. **Q21 — blocker — the optional-null fix also permits null mandatory fingerprints.**  
   [run_tg1_chain.py:406](<repo>/benchmark/chains/c147/run_tg1_chain.py:406) pins any present value, including null. [chain_ops.py:620](<repo>/benchmark/bench/chain_ops.py:620) then compares equality without validating mandatory identities.

   A manifest with `opencode_exe_sha256=None` and `universe_sha256=None` successfully pinned; its otherwise complete leg returned `validate_leg == []`. **Change:** allow null only for explicitly optional identities such as `agent_system_sha256`. Require valid mandatory hashes before acknowledgement, pinning and completion. Test null, absent and malformed values separately.

4. **Q22 — should-fix — the transport cutoff still precedes actual signalling.**  
   [tg1_runner.py:534](<repo>/benchmark/bench/tg1_runner.py:534) captures the byte cutoff before calling `graceful_stop`. That method performs [the process/memory scan:468](<repo>/benchmark/bench/proc_guard.py:468) before [SIGTERM:476](<repo>/benchmark/bench/proc_guard.py:476).

   A registered transport error emitted during that scan, before SIGTERM, was tolerated and reconciled successfully. **Change:** capture the cutoff through a callback immediately before the actual client signal, after scanning and identity verification; leave tolerance disabled if no signal is sent. Test an error produced during the pre-signal scan.

5. **Q23 — should-fix — valid collection-error finals are rejected as incomplete legs.**  
   [structured_grade.py:393](<repo>/benchmark/bench/structured_grade.py:393) emits `missing_report` when Python produces no XML. [parse_python:169](<repo>/benchmark/bench/structured_grade.py:169) deliberately accepts this for a collection error, yielding a scored failure. But [FINAL_OUTCOMES:416](<repo>/benchmark/bench/structured_grade.py:416) excludes it.

   The existing [collection-error test:125](<repo>/benchmark/bench/tests/test_c147_grade_reports.py:125) proves the producer accepts this outcome; final-receipt validation rejects it. **Change:** distinguish a typed, permitted collection-error outcome from infrastructure failure, retain stdout/stderr, and test its final row through both verifiers.

6. **Q24 — should-fix — non-parsed receipts need only an unrelated artifact.**  
   [structured_grade.py:476](<repo>/benchmark/bench/structured_grade.py:476) requires language-specific artifacts only for `parsed`. Final `timeout`, `oom` and `mem_kill` receipts containing one hashed `unrelated.bin` each returned no validation errors.

   **Change:** require the launch-output artifacts for every grade that ran: Python stdout/stderr, or Go JSONL/stderr; additionally require XML for parsed Python. Preserve the explicit artifact-free tampered exception. Add mutations for every early-return outcome.

7. **Q25 — blocker — missing inject run IDs bypass all live clearance checks.**  
   [inject_verify.py:346](<repo>/benchmark/m62/inject_verify.py:346) performs live checks only when `run_id` is truthy; [verify_row:175](<repo>/benchmark/m62/inject_verify.py:175) does not require it.

   Removing `run_id` from all three otherwise passing fixture manifests produced **`RESULT PASS`, rc 0**, without calling either live checker—even with leftover processes/containers supplied by those checkers. **Change:** require a valid run identity before PASS and perform live checks for every retained passing attempt. Missing or malformed identity must fail.

Q1–Q18 status against the code:

| ID | Status | Evidence |
|---|---|---|
| Q1 | **Partial** | Identity-based signals implemented; unload remains unsafe. `chain_ops.py:439–452`; Q19. |
| Q2 | **Partial** | Edit deletion and recursive clearing removed; replacement-directory deletion remains. `proc_guard.py:922`, `854`; Q20. |
| Q3 | **Answered** | Top-level receipt emitted and consumed. `tg1_runner.py:1228`, `run_tg1_chain.py:158`; real-manifest test `test_c147_chain_runner.py:923`. |
| Q4 | **Partial** | Row scaffold/model/overlay checked, but mandatory identities and report validation retain gaps. `chain_ops.py:641–663`; Q21/Q24. |
| Q5 | **Answered** | Latest unreadable attempt retained; missing requested kind fails. `inject_verify.py:304–327`. |
| Q6 | **Answered under B8 decision** | Successful-completion increase rejected; observation labelled consistency. `inject_verify.py:125–145`, `166`. |
| Q7 | **Answered** | Cancel rechecked after terminal phases, before returning for row commitment. `tg1_runner.py:383–395`. |
| Q8 | **Partial** | Exact messages and multiplicity bounded; cutoff still precedes actual signal. `token_turn_gate.py:388–412`; Q22. |
| Q9 | **Answered** | Denied tracked inspection becomes uncertainty through direct identity audit. `proc_guard.py:618–659`. |
| Q10 | **Answered** | Typed tampered final receipt emitted and accepted explicitly. `tg1_runner.py:770–772`, `structured_grade.py:468–472`. |
| Q11 | **Answered** | Escalation checks identity, metrics, events, rows and heartbeat changes. `run_tg1_chain.py:545–575`. |
| Q12 | **Partial** | Listener acquisition proves ancestry; destructive HTTP still lacks current endpoint ownership. `chain_ops.py:296–301`, `377`; Q19. |
| Q13 | **Partial against stated decision** | Write-only and regular-file content matching implemented; directory branch bypasses matching. `proc_guard.py:922–925`, `854`; Q20. |
| Q14 | **Partial** | Optional null now pins correctly; mandatory nulls also accepted. `run_tg1_chain.py:399–417`; Q21. |
| Q15 | **Partial** | Shared schema rejects malformed/absent reports, but producer/validator mismatch and early-outcome artifact gaps remain. `structured_grade.py:428–484`; Q23/Q24. |
| Q16 | **Partial** | Complete messages and byte offsets implemented; pre-signal scan remains outside the cutoff. `tg1_runner.py:534`, `proc_guard.py:468`; Q22. |
| Q17 | **Answered** | Direct tracked-identity audit; denied verification returns unknown/false. `proc_guard.py:483–506`, `618–659`. |
| Q18 | **Answered against stated decision** | `cancellation_consistent` accepted and explicitly disclosed as uncorrelated. `inject_verify.py:125–145`, `338–342`; C149 at `docs/open-questions.md:18`. |

Re-verification of P findings previously partial or unanswered:

| ID | Status | Code evidence |
|---|---|---|
| P1 | **Partial** | Accepted write/content rule has the directory bypass. `proc_guard.py:854`, `922`; Q20. |
| P3 | **Partial** | Process cleanup is ownership-aware; runner HTTP teardown remains unsafe. `proc_guard.py:592–598`, `chain_ops.py:377`; Q19. |
| P4 | **Answered** | Terminal cancellation and computed cooperative deadline. `tg1_runner.py:378–395`, `chain_ops.py:503–506`. |
| P10 | **Answered under B8 decision** | Descendant kill, verified termination, bounded wait and cancellation consistency checked. `inject_verify.py:148–169`. |
| P11 | **Partial** | Provenance comparisons exist, but mandatory null fingerprints pass. `chain_ops.py:618–622`; Q21. |
| P12 | **Partial** | Launch-time retention works; report acceptance remains incomplete. `structured_grade.py:371–408`, `476`; Q23/Q24. |
| P13 | **Answered for the registered offline contract** | Real-client cancel tests and default-null pilot/full contract tests exist. `test_c147_cancel.py:210`, `test_c147_chain_runner.py:937–957`. Live composition remains pending as specified. |
| P15 | **Partial** | Latest-attempt handling works; absent run IDs bypass live checks. `inject_verify.py:304–308`, `346`; Q25. |
| P17 | **Partial** | Barrier/escalation checks implemented; teardown endpoint ownership remains incomplete. `run_tg1_chain.py:452–507`, `545–575`; Q19. |
| P19 | **Answered** | Descriptor seeds, mandatory row overlay hash and aborted-resume refusal. `chain_ops.py:606–608`, `637–646`, `tg1_runner.py:1078–1083`. |

P2, P5–P9, P14, P16, P18 and P20–P22 retain their earlier **answered** status; they were not re-reviewed beyond regression checks, as requested.

The §9 findings against code:

| Finding | Assessment |
|---|---|
| B1 | SIGTERM-first, 15-second grace, survivor SIGKILL and model-role SIGKILL implemented at `tg1_runner.py:537–556`. Both transport messages are pinned at `token_turn_gate.py:383–396`. **Q22 still broadens §3a beyond the stated own-signal exception.** |
| B1b | Trailing aborted usage is validated and charged once, including terminal checks: `token_turn_gate.py:469–476`, `504–506`. No additional weakening found. |
| B2 | Alloc threshold is **512 MiB**, command allocates **1 GiB**: `tg1_runner.py:42`, `50–52`. Campaign constants unchanged. |
| B3 | Registered killed-command alternatives implemented at `inject_verify.py:113–121`; pinned-client test checks fixture SHA and exact normalized content at `test_c147_inject.py:375–383`. No §3a weakening found. |

Campaign policy hashing remains pinned to `ba86ba16…`; its tests passed. Explicit inject rows are rejected by campaign validation, and resume refuses inject/campaign mixing. I found no personal home paths or PII in the inspected committed additions. The new counterexamples identify missing boundary tests despite the passing suites. Live inject clearance and the real pilot remain pending.

not cleared
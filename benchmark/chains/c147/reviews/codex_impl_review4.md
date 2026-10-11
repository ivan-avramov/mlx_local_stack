Reviewed HEAD `6bb4cefe`. **607 tests passed**; `git diff --check` passed; working tree clean. No repository files changed.

1. **Q26 — blocker — destructive HTTP calls retain ownership gaps.**  
   [chain_ops.py:357](<repo>/benchmark/bench/chain_ops.py:357) sends `/v1/models/load` without rechecking router ownership. A mocked replacement listener received that request; model loading can terminate its existing worker.

   The new unload guard also has a gap: [385](<repo>/benchmark/bench/chain_ops.py:385) permits “no worker,” then [397](<repo>/benchmark/bench/chain_ops.py:397) independently scans again and sends unload if a worker appears. My counterexample sent unload with `worker_started=None` and returned `True`.

   **Change:** share a router-identity guard across destructive HTTP calls. For unload, return immediately when the guarded scan finds no worker; otherwise require the recorded worker identity before sending. Test endpoint replacement before load and worker appearance between unload scans.

2. **Q27 — blocker — emptied-parent cleanup can delete a replacement directory.**  
   [proc_guard.py:892](<repo>/benchmark/bench/proc_guard.py:892) calls `rmdir` without revalidating the parent’s recorded identity.

   A temporary-files counterexample unlinked the matching model-written file, renamed its original parent, and created an unrelated empty directory at the original name. Cleanup deleted the replacement and reported it in `tmp_cleaned`; the original parent survived. This exceeds B8’s accepted cleanup rule and the stated final-check→unlink residual.

   **Change:** retain and revalidate each parent directory’s inode/device immediately before removing its name. A replacement must remain diagnostic. Add this replacement-after-file-unlink test.

3. **Q28 — should-fix — failed SIGTERM attempts still enable transport tolerance.**  
   [proc_guard.py:482](<repo>/benchmark/bench/proc_guard.py:482) invokes the cutoff callback before signalling, but [488](<repo>/benchmark/bench/proc_guard.py:488) swallows failed signalling without invalidating it.

   With `terminate()` raising `AccessDenied`, `graceful_stop` returned `[]`, yet the cutoff remained set and a subsequent registered transport error reconciled successfully as `stalled`.

   **Change:** commit the cutoff only when SIGTERM succeeds; disable tolerance when no client was signalled. Test `AccessDenied` and `NoSuchProcess` during signalling.

The requested Q1–Q25 disposition follows. Paths below are under `benchmark/`; gate paths are under `scripts/`.

| ID | Status | Code evidence |
|---|---|---|
| Q1 | partial | Identity-bound teardown at `bench/chain_ops.py:459`; destructive HTTP gap remains Q26. |
| Q2 | partial | Completed-write/content checks at `bench/proc_guard.py:930`; parent replacement remains Q27. |
| Q3 | answered | Top-level receipt emitted at `bench/tg1_runner.py:1231`, consumed at `chains/c147/run_tg1_chain.py:158`. |
| Q4 | answered | Manifest/row identities, seeds, evidence and reports checked at `bench/chain_ops.py:651`, `680`, `699`, `707`. |
| Q5 | answered | Latest unreadable attempt retained at `m62/inject_verify.py:309`; missing requested kind fails at `329`. |
| Q6 | answered under B8 | Completion-counter increase rejected at `m62/inject_verify.py:143`; observation labelled consistency at `167`. |
| Q7 | answered | Terminal cancellation checked before returning the item at `bench/tg1_runner.py:383`. |
| Q8 | partial | Exact messages, multiplicity and byte offsets at `bench/token_turn_gate.py:388–412`; failed-signal gap Q28. |
| Q9 | answered | Denied tracked inspections become uncertainty at `bench/proc_guard.py:617`, `628–659`. |
| Q10 | answered | Typed tampered final at `bench/tg1_runner.py:775`; explicit validation at `bench/structured_grade.py:475`. |
| Q11 | answered | Escalation rechecks worker identity, metrics, events, rows and heartbeat at `chains/c147/run_tg1_chain.py:556–568`. |
| Q12 | partial | Router acquisition proves ancestry at `bench/chain_ops.py:296`; HTTP ownership remains Q26. |
| Q13 | partial against B8 | Write-only/content matching at `bench/proc_guard.py:930`, `874`; emptied-parent replacement remains Q27. |
| Q14 | answered | Optional null pins as a value at `chains/c147/run_tg1_chain.py:406`; mandatory validation at `bench/chain_ops.py:580`. |
| Q15 | answered | Shared receipt schema at `bench/structured_grade.py:435`; both verifiers consume it at `bench/chain_ops.py:709`, `m62/inject_verify.py:101`. |
| Q16 | partial | Complete messages and byte cutoff implemented; unsuccessful signalling still arms tolerance—Q28. |
| Q17 | answered | Direct tracked-identity audit at `bench/proc_guard.py:628`; unknown cannot pass `verify_gone` at `507`. |
| Q18 | answered against B8 | `cancellation_consistent` implements and discloses the accepted inference at `m62/inject_verify.py:126–146`, `344`. |
| Q19 | partial | Recorded endpoint/worker checks added at `bench/chain_ops.py:377`; no-worker/rescan gap remains Q26. |
| Q20 | answered | A write candidate replaced by a directory is retained at `bench/proc_guard.py:864–868`. Q27 concerns its parents. |
| Q21 | answered | Mandatory hashes validated at `bench/chain_ops.py:580`; enforced at barrier, pinning and completion at `run_tg1_chain.py:485`, `402`, `chain_ops.py:670`. |
| Q22 | partial | Callback moved after scanning at `bench/proc_guard.py:482`; unsuccessful signals remain Q28. |
| Q23 | answered | Collection error typed at `bench/structured_grade.py:408`; permitted final at `421`. |
| Q24 | answered | Launch outputs required for every grade that ran at `bench/structured_grade.py:483–487`. |
| Q25 | answered | Run ID required at `m62/inject_verify.py:185`; every retained PASS receives suite live checks at `350–355`. |

Rechecked only the design findings marked partial or unanswered in round 1:

| ID | Status | Code evidence |
|---|---|---|
| P1 | partial against B8 | Write/content safeguards at `bench/proc_guard.py:930`, `874`; Q27 remains. |
| P3 | partial | Owned-resource cleanup at `bench/proc_guard.py:628`; destructive HTTP ownership remains Q26. |
| P4 | answered | Terminal cancel/evidence handling at `bench/tg1_runner.py:378`; computed deadline at `bench/chain_ops.py:519`. |
| P10 | answered under B8 | Kill, descendant, reconciliation and cancellation-consistency checks at `m62/inject_verify.py:149–172`. |
| P11 | answered | Mandatory provenance and pinned comparisons at `bench/chain_ops.py:580`, `667`; driver hashes retained at `run_tg1_chain.py:193`. |
| P12 | answered | Output retention from launch at `bench/structured_grade.py:371`; exception indexing at `304`; shared validation at `435`. |
| P13 | answered for offline contract | Real entry-point cancellation tests in `bench/tests/test_c147_cancel.py`; default-null contract test at `test_c147_chain_runner.py:1025`. Live composition remains pending. |
| P15 | answered | Latest-attempt aggregation, report validation and mandatory live-check identity at `m62/inject_verify.py:309`, `101`, `185`, `350`. |
| P17 | partial | Barrier and escalation checks at `run_tg1_chain.py:488`, `549`; lifecycle ownership remains Q26. |
| P19 | answered | Descriptor seeds/overlay checks at `bench/chain_ops.py:653`, `684–693`; aborted resume refused at `bench/tg1_runner.py:1081`. |

**P2, P5–P9, P14, P16, P18 and P20–P22 retain their earlier answered status**, without fresh full re-verification.

| §9 finding | Code assessment |
|---|---|
| B1 | SIGTERM-first, 15-second grace and survivor/model SIGKILL at `bench/tg1_runner.py:540–559`; both transport messages pinned at `bench/token_turn_gate.py:383–396`. **Q28 still broadens §3a beyond successful own signalling.** |
| B1b | Trailing aborted usage validated and charged at `bench/token_turn_gate.py:469–476`, `504–506`. No additional weakening found. |
| B2 | Alloc threshold is **512 MiB**, command allocates **1 GiB** at `bench/tg1_runner.py:42`, `50–52`. Campaign constants unchanged. |
| B3 | Killed-command alternatives at `m62/inject_verify.py:114–123`; real-client fixture SHA/content checks at `bench/tests/test_c147_inject.py:375–383`. No additional §3a weakening found. |

Campaign policy remains pinned to `ba86ba16…`. Inject/campaign labels and resume identities remain separated, and campaign completion rejects inject-labelled rows. I found no personal home paths or PII in the inspected committed additions. The three counterexamples lack corresponding boundary tests.

The operator’s V3 and pilot remain the real functional clearance. These findings would not invalidate an ordinary positive run, but that run would not establish safety under endpoint replacement, directory replacement or failed signalling.

not cleared
P1  
Location: `benchmark/bench/p426_wave2.py::_check_recheck_ack_args`  
Severity: major  
Evidence: confirmed  
Problem: CLI validation rejects the historical resume command `--recheck-ack <sha>` before loading the already-acknowledged legacy sequence. `ensure_recheck` supports that legacy record, but is never reached.  
Concrete failure scenario: Resume S29-P13 using its original command. `check_args` raises `fz.Refusal` despite `sequence.json` already containing the accepted actor-less acknowledgement. The tests miss this because legacy-resume coverage calls `ensure_recheck` directly.  
Proposed change: When a matching acknowledgement is already recorded, permit the legacy flag form. Otherwise require actor and ruling before mutation. Add an end-to-end CLI/check-args legacy-resume test.

P2  
Location: `benchmark/bench/p426_panel.py::KV_FROZEN_RUBRICS` and `_kv_rubric_ok`  
Severity: major  
Evidence: confirmed  
Problem: The compatibility exception is scoped to member A3, not to the exact frozen A3 record. Consequently, any A3 manifest can use the obsolete `vision` rubric and SHA and pass validation. This goes beyond preserving the frozen record.  
Concrete failure scenario: A stale or newly assembled A3 panel export binds `vision` and `5987d169…97b8`; `_kv_rubric_ok` accepts it even though new exports must bind `kv-vision`. Existing tests cover the genuine frozen record and the normal new exporter, but not rejection of a non-frozen record using the legacy pair.  
Proposed change: Bind the legacy exception to the immutable identity/hash of the known frozen A3 artifact, and add a negative test for a newly created A3 record carrying the old pair.

P3  
Location: `benchmark/bench/p426_wave2.py::recheck_ack_actor` and `Sequencer.ensure_recheck`  
Severity: minor  
Evidence: confirmed  
Problem: Any non-empty ruling is interpolated raw into a line-oriented log. Embedded newlines or control characters can create forged-looking log entries.  
Concrete failure scenario: `--recheck-ack-ruling $'C383\nRE-CHECK s1: acknowledged by the operator'` records valid JSON but emits multiple misleading log lines. Tests use only ordinary one-line rulings.  
Proposed change: Reject CR/LF and control characters in rulings, or encode the ruling before logging; add a multiline-ruling test.

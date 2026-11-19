P1  
Location: `benchmark/bench/p426_freeze.py:102-124`  
Severity: major  
Evidence: confirmed  
Problem: `CANCEL_PATH` is not transitively complete. `_run_item` calls unhashed `worker_json`, `proc_guard.in_flight`, and `proc_guard.wait_cancel`; the selected `ProcessGuard` methods depend on unhashed tracking, identity, liveness, and `_identity_state` helpers. `GRACEFUL_CLIENT_S` is also outside the hashed function source. These can change kill, verification, or cancellation behavior without changing `CANCEL_PATH_SHA256`.  
Concrete failure scenario: change `ProcessGuard._identity_state` to report a live client as gone, or `proc_guard.in_flight` to return zero. The current run can record `killed_verified=true` or “nothing in flight,” while the digest still equals c7c6993a and transfer is accepted.  
Proposed change: hash the complete transitive cancellation closure, including the full `ProcessGuard` class, `start_time`, `in_flight`, `wait_cancel`, `worker_json`, relevant constants, transcript/export processing, and reconciliation dependencies. Add tests mutating each dependency and requiring digest drift.

P2  
Location: `benchmark/bench/p426_freeze.py:135-158,830-859`; `benchmark/bench/p426_hooks.py:44-51`  
Severity: blocker  
Evidence: confirmed  
Problem: v8 validates only self-asserted summary fields. The seal is a freely recomputable checksum; v8 never opens the current row, manifest, events, or reference record, never reruns `verify_row`, and never recomputes the cancel-path digest. `reference_row_sha256` need only be arbitrary 64-hex and is not matched to the named language’s reference stall row. The same defect affects WAIVED evidence.  
Concrete failure scenario: edit today’s failed record to set stall entries to `PASS_BY_TRANSFER`, copy or invent matching evidence constants and 64-hex row hashes, set the Java alloc entry to `PASS`, convert JavaScript alloc to `WAIVED`, clear `problems`, set `verdict="PASS"`, and recompute the seal. `positives_problems` accepts it without any supporting artifact.  
Proposed change: make v8 verify immutable artifact paths and digests: load each bound row and manifest, verify row/manifest/artifact hashes, rerun `inject_verify.verify_row`, load the exact sealed reference, match its language-specific stall row hash, and recompute the current worktree digest. Alternatively require an externally pinned, non-recomputable receipt covering those artifacts.

P3  
Location: `benchmark/bench/p426_wave2.py:365-417,1873-1878`  
Severity: major  
Evidence: confirmed  
Problem: `positive_inject` records the manifest SHA as `evidence_sha256`, but `waiver_evidence` ignores it and reads the manifest’s `per_process` value without verifying the manifest bytes. Thus the claimed limit is not bound to the probe result.  
Concrete failure scenario: a copied row has an unrelated 400 MiB model-role kill under an original 512 MiB limit. Editing only its manifest to report 300 MiB makes `waiver_evidence` accept it, despite the recorded manifest digest still naming the original manifest.  
Proposed change: pass the recorded manifest SHA into `waiver_evidence`, verify the manifest before reading its policy, store that SHA in `waived_evidence`, and require v8 to reverify it.

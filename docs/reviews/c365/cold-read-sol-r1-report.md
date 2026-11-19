P1  
Location: `benchmark/bench/tests/test_c147_cancel.py:356-365`  
Severity: major  
Evidence: confirmed — traced  
Problem: `graded.set()` runs in `finally`, so it signals completion even when the snapshot grader raises.  
Concrete failure scenario: `sg.grade()` raises; `GradeWorker` records the failure and exits, but the firing thread sends SIGTERM first. Cleanup skips `worker.finish()` when the worker is already dead (`arm_runner.py:847-849`), preserving exit 143. All test assertions can then pass while a grader defect was masked.  
Proposed change: set the event only after a successful non-final grade for boundary 1, then return its result.

P2  
Location: `benchmark/bench/tests/test_c147_cancel.py:366-375`  
Severity: major  
Evidence: confirmed — traced  
Problem: the daemon firing thread is never cancelled or joined. It unconditionally sends SIGTERM at the deadline even if the test has already failed and restored the prior handler.  
Concrete failure scenario: a provenance or setup regression makes `f["run"]` exit before the marker/grade condition. The test fails, but up to 30 seconds later its daemon thread sends SIGTERM during another test, causing an unrelated `SystemExit(143)` or terminating pytest and hiding the original defect.  
Proposed change: add a stop event, set it in `finally`, join the thread, and suppress SIGTERM when the test has already unwound.

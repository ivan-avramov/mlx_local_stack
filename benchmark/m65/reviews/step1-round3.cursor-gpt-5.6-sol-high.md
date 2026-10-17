Connection lost, reconnecting to https://agentn.us.api5.cursor.sh (attempt 1)...
Retry attempt 1...
G21 — high — `benchmark/bench/tg2_grade.py:870-909`  
Failure: cleanup is not guaranteed. Volumes are unregistered; holder-removal timeouts can skip volume cleanup; cleanup failures are suppressed when grading already failed. Process death can leave the holder retaining tmpfs memory for two hours.  
Fix: track volumes with verified recovery/startup sweeping, continue cleanup after all removal exceptions, and always surface cleanup uncertainty while preserving the original exception.

G22 — medium — `benchmark/bench/tg2_grade.py:945-955`  
Failure: collect timeout/OOM/memory-kill after its valid marker becomes `crash`, unlike compile/execute resource outcomes.  
Fix: classify collect resources before generic report failure, using its 32-MB output limit.

G23 — medium, non-blocking verification — `benchmark/bench/tests/test_tg2_grade.py:351-363,1206-1323`  
Failure: tests use pytest `tmp_path`, normally beneath `/var/folders` on macOS, so P361 refuses before fake or real Docker paths run.  
Fix: allocate grading trees beneath `$STACK_WORKDIR`; add real-Docker hostile-report and interrupted-cleanup tests.

G24 — low, non-blocking hardening — `benchmark/bench/tg2_grade.py:323-348`  
Failure: duplicate tar member keys are last-wins and bypass the unique-key count.  
Fix: reject duplicate normalized keys and verify extracted length equals the declared size.

Staging otherwise preserves regular-file bytes and modes through `cp -a`. Tamper remains relative to the prepared manifest on the pre-stage snapshot. Raw uncompressed tar, traversal, hardlinks, symlinks, sparse-size abuse, and compression bombs are bounded or rejected.

VERDICT: NOT CLEARED

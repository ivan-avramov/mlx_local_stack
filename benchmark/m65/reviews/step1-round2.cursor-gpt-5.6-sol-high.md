Round-1 disposition: G1–G14, G16, and G17 are resolved. G15 is only partially resolved.

G18 — blocker — `benchmark/bench/tg2_grade.py:813-841`  
Failure: host-side report reads follow model-created symlinks and accept non-regular Java report entries. A test can expose host files or make grading block/read indefinitely via a symlink, FIFO, or device.  
Fix: traverse every component without following symlinks; require regular files; open with `O_NOFOLLOW`, verify with `fstat`, and bounded-read the same descriptor.

G19 — high — `benchmark/bench/tg2_grade.py:43-50,229-235,813-833`  
Failure: G15’s limits remain per-process/per-file, not aggregate. The writable host bind mounts have no quota; Java alone permits 2,000 reports of up to 32 MB each, while arbitrary extra files remain unlimited. Model code can exhaust host storage before post-run checks.  
Fix: use quota-bounded per-grade storage and enforce a cumulative report limit during execution and parsing.

G20 — low, non-blocking — `benchmark/m65/tg2_image/build.sh:17-22`  
Failure: `js_lock_sha256` hashes `shasum` output containing the absolute checkout path. The recorded value is path-dependent and differs from the lock’s actual SHA-256. The correct context digest is embedded in the verified image, so this does not affect current grading.  
Fix: hash file bytes directly or run the aggregation from a fixed relative directory.

The implementer notes are sound: Java `editor` files include `Winner.java` and the real connect test passed; fresh reference directories avoid stale bind views; independent Docker inspection correctly makes OOM state tri-state.

Verification: 243 targeted tests passed, 11 real-container tests passed, and image acceptance passed for `sha256:09f2b30e95b114985c2207a8cc855c90275a3f065baecf509f3b006e733389fa`. The image’s `polyglot_sha` and staged-context labels match recomputed values.

VERDICT: NOT CLEAREDAll verification tasks passed. No follow-up action is needed; the G18/G19 blockers remain, so the review verdict is unchanged: NOT CLEARED.

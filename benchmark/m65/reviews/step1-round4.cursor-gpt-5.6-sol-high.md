G25 — blocker — `benchmark/bench/tg2_grade.py:966-1014`  
The sweep does not prove ownership. It selects every object carrying the static `mlxbench.tg2=1` label, without checking its name or matching it against the registry; the registry is consulted only after deletion. Missing or malformed creation labels become `0`, making such objects immediately old. Post-removal verification proves absence, not that the removed object was created by tg2. An old foreign object carrying that label is deleted.

G26 — high — `benchmark/bench/tg2_grade.py:896-914,966-1002`  
The age gate does not protect live grades. Labels are timestamped once, the default threshold is 3600 seconds, but a grade may run five timeout-bounded phases; production acceptance passes `timeout=900`, and the holder is intentionally retained for 4800 seconds. A concurrent sweep can therefore remove an active grade’s holder and volumes. The registry is not used to exclude active work.

G27 — high — `benchmark/bench/tg2_grade.py:733-789,966-1015`  
Recovery sweeping is not wired into any production path. Repository-wide references to `sweep_leftovers()` are tests only. The SIGKILL test manually invokes it, so it proves the primitive, not startup recovery. After real process death, the holder eventually exits but its container and volumes remain indefinitely. G21’s guaranteed recovery/startup sweep is therefore incomplete.

G28 — medium, non-blocking verification — `benchmark/bench/tests/test_tg2_grade.py:1450-1472`  
The real-Docker hostile-report test relies on a fixed four-second race. If Jest has not finished, FIFO replacement can block report writing or later Jest output can overwrite the hostile object, producing a timeout or benign report rather than the asserted crash. Use deterministic synchronization.

Prior findings:
- G21: local cleanup continuation, registration, verification, and uncertainty propagation are correct; recovery and sweep safety are not.
- G22: fixed. Collect timeout/OOM/memory-kill is classified before report failure, while `parse_collect` retains the 32 MB bound.
- G23: test trees are outside `/var/folders`; real-Docker hostile and SIGKILL paths reach production grading/sweep code, subject to G28 and G27.
- G24: fixed. Exact duplicate member keys and short extraction are rejected; accepted Java paths cannot alias to one output key.

The later main merge does not modify either reviewed file.

VERDICT: NOT CLEARED

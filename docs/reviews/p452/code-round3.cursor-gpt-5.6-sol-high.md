F1 — CLOSED — M1 now requires and propagates its mini-wave freeze’s `production_ref`; Wave-1 v4 intentionally excludes M1 and missing provenance fails closed.

F2 — OPEN — PID/create-time matching fixes reuse, but `orchestrate.py:1213-1229` still exempts launcher modules without validating expected argv, leaving the misbehaving-launcher case unresolved.

F3 — CLOSED — Custom refs are fully resolved and validated; retaining the immutable default pin’s historical abbreviated reporting is an acceptable fail-closed compatibility residual.

F4 — OPEN — The tests now call real `preflight`, but `test_p452_qualify_in_wrapper.py:105-177` still tests only wrapper→child, not sequencer→wrapper→qualify or report creation, so sequencer exemption/provenance regressions remain uncovered.

H1 — MEDIUM — `dev/p369_phase2/orchestrate.py:1258-1261,1290-1295`: PID identity uses `psutil.create_time()`, which is known to shift on macOS when boot time is clock-adjusted. If it shifts between ancestor collection and process census, the same legitimate ancestor gets different identities and M1 refuses as foreign. Use an unadjusted kernel start-time helper for both reads and add a boot-time-shift regression test.

VERDICT: DISAGREE F2 F4 H1

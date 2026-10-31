R9 — answered — `benchmark/bench/tests/test_c151_start_time.py:135-179`. Every exemption uses an exact file, qualname, receiver, and method; `Chain.run_step` is exact.

R10 — answered — `benchmark/bench/proc_guard.py:85-109,681-689,752-766`; tests `benchmark/bench/tests/test_c151_start_time.py:243-278`. ESRCH, EPERM/EACCES, and unexpected errno map as specified. The untracked denied-order counterexample now produces completed-but-uncertain status and names the PID.

R11 — answered — `benchmark/bench/chain_ops.py:121-151`; tests `benchmark/bench/tests/test_c151_start_time.py:281-295`. Each link uses monotonic order when both operands are readable; otherwise that entire link uses wall time. No cross-domain comparison occurs within a link.

R12 — HIGH — persistent unexpected `start_order()` failure prevents cleanup completion — `benchmark/bench/proc_guard.py:367-375,460-479,524-537,659-770`. Killing the monitor is the correct fail-closed response: `TransportAbort` is deliberately not transient. However, `cleanup()` calls `kill_role()`, which calls `tick()` again; a persistent EINVAL propagates before container removal, final process sweep, and `_status` publication. I reproduced an owned process being killed but `status.completed=False`; registered containers would not be handled.

Concrete change: retain monitor death as fatal, but capture cleanup-time order failures, complete tracked-process and container cleanup, publish completed/uncertain status, then raise. Add a persistent-EINVAL cleanup test.

R13 — MEDIUM — the opencode test retries behavior absent from production — `benchmark/bench/tests/test_opencode_v2_probe.py:929-945`; production `benchmark/run_opencode_probe_v2.py:447-463`. The test-only wrapper hides the known SQLite-lock race, while a live probe still immediately transport-aborts on that same race.

Concrete change: put the narrowly bounded `"database is locked"` retry in the production export path, then remove the test monkeypatch so the real test exercises it.

R14 — LOW — survivor check treats AccessDenied as proof of exit — `benchmark/bench/tests/test_c147_inject.py:373-378`. Catching all `psutil.Error` includes `AccessDenied`, whereas production correctly treats denied identity inspection as unknown (`benchmark/bench/proc_guard.py:576-599`).

Concrete change: catch only `psutil.NoSuchProcess`; AccessDenied should fail the assertion explicitly.

No ordinary R10 false-abort evidence: all 522 current same-UID live processes had readable start order. A 1,000-process exit stress produced only successful live/zombie reads and ESRCH after reap, supporting the unexpected-errno fail-closed classification rather than C148-style transience.

Prescribed suite: 220 passed.

not clearedPrescribed C151 suite passed: 220 tests in 2.97s. No follow-up action needed.

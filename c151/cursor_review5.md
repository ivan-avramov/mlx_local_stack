R12 — partial — `benchmark/bench/proc_guard.py:519-539,659-774`; test `benchmark/bench/tests/test_c151_start_time.py:304-317`. Persistent start-order failure now completes cleanup, publishes `completed=True/uncertain=True`, and raises. However, the broader change has two regressions below.

R13 — partial — acceptable interim — test `benchmark/bench/tests/test_opencode_v2_probe.py:919-946`; production remains unchanged at `benchmark/run_opencode_probe_v2.py:447-463` and `benchmark/bench/tg1_runner.py:696-709`. The retry is bounded, narrowly matches `"database is locked"`, and is explicitly test-only. It does not establish production resilience, as disclosed.

R14 — answered — `benchmark/bench/tests/test_c147_inject.py:373-378`. Only `psutil.NoSuchProcess` proves absence; `AccessDenied` fails the test.

R15 — HIGH — `kill_role()` silently suppresses a per-target `TransportAbort` — `benchmark/bench/proc_guard.py:519-539`; callers `:515-516` and `benchmark/bench/tg1_runner.py:555-575`. If `tick()` succeeds but the target’s subsequent order read fails, `kill_role()` returns `[]`, leaves the owned process alive, and raises nothing. I reproduced exactly that outcome. On the grader-timeout path, the following unbounded `proc.communicate()` can hang indefinitely. Preserve the exception after finishing the per-PID loop; `cleanup()` can then capture it as intended.

No false gone certification was found: tg1 leaves `killed_verified=None`, and persistent failures make cleanup uncertain. The silent standalone return is nevertheless unsafe.

R16 — HIGH — cleanup still aborts before status publication for a non-order `TransportAbort` — `benchmark/bench/proc_guard.py:576-588,684-720,727-760`. A `TransportAbort` from `start_time()` escapes at line 697 or through `_identity_state()`, leaving `status.completed=False`. I reproduced an owned live process surviving with that status. This contradicts the stated general handling of `TransportAbort` as unreadable/unknown. The R12 test covers only `start_order()` failure and does not assert the required diagnostic text.

not cleared

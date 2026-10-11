R1 — partial — `benchmark/bench/proc_guard.py:104-114`. Changed fields now include before/after values. Same-valued missing fields still produce only `empty field`, consistent with the lead’s accepted partial scope.

R2 — not answered — `benchmark/bench/proc_guard.py:236,270-271,307-329,620-625`. The lead missed a fail-open path; see R8.

R3 — answered — `benchmark/bench/chain_ops.py:122-143`. The explicit walk matches psutil 7.2.2 semantics for lowest PID 0/1, parent reuse, `NoSuchProcess`, zombies, and propagated `AccessDenied`. The live Darwin chain included PID 0.

R4 — answered — `benchmark/bench/tests/test_c151_start_time.py:27-35,47-61`. The fixture establishes zero initial adjustment and tests both ±1 second.

R5 — partial — `benchmark/bench/tests/test_c151_start_time.py:135-160`. It scans the intended trees platform-independently, but its broad exemptions weaken enforcement; see R9.

R6 — answered — `benchmark/bench/tests/test_c151_start_time.py:124-132`. The real child remains `"alive"` and `verify_gone()` returns false after the shift.

R7 — answered — `benchmark/bench/proc_guard.py:42-54`; `benchmark/bench/tests/test_c151_start_time.py:77-82`; `benchmark/requirements-bench.lock:150`. Darwin psutil objects fail closed without the raw path. Normal `NoSuchProcess`/`AccessDenied` remain transient where previously tolerated; `TransportAbort` from a missing private path aborts rather than falsely clearing cleanup.

R8 — HIGH — false cleanup clearance after a backward wall-clock step — `benchmark/bench/proc_guard.py:236,270-271,307-329,620-625`. A client registered before the step can spawn an indirect descendant afterward whose raw start time is less than `started`. `_protected()` excludes that child from ancestry tracking and cleanup. Killing the tracked client then leaves the child alive while cleanup reports `completed=True`, `uncertain=False`, and no survivors. I reproduced exactly that state with the process fakes.

Concrete change: replace the temporal protection boundary with a guard-creation snapshot of pre-existing `(pid, start_time)` identities. Add a test where a tracked client at time 110 has a post-step child at time 99 with `started=100`; cleanup must kill it or report uncertainty, never clean clearance.

R9 — MEDIUM — AST guard can silently permit recurrence — `benchmark/bench/tests/test_c151_start_time.py:135-138,152-159`. Every `.create_time()` anywhere in `proc_guard.py` is allowlisted, and every `self.*`/`self.ops.*` call in any class is exempted. This does not currently hide an unintended production call, but it does not enforce the claimed invariant.

Concrete change: make exemptions context-specific—`create_time()` only inside `proc_guard.start_time`, `self.create_time/self.parents` only inside `ChainOps`, and `self.ops.create_time` only at the known chain effect-hook site. Parse failures should fail rather than be skipped.

Prescribed suite: 163 passed.

not cleared

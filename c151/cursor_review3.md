R8 — answered — `benchmark/bench/proc_guard.py:288-330,360-383,677-694`; tests `benchmark/bench/tests/test_c151_start_time.py:195-231`. Identity and ordering are cleanly separated; the backward-step counterexample is closed.

R9 — partial — `benchmark/bench/tests/test_c151_start_time.py:135-177`. Parsing now fails closed and receiver/method matching is improved. However, `("*", "self.ops", "create_time")` permits the call in every qualname in `run_tg1_chain.py`; I confirmed unrelated methods/classes are accepted. Replace it with `ChainRunner.run_step`; preferably replace `ChainOps.*` with the exact current methods too.

R2 fail-open recheck — partial. The wall-clock fail-open is fixed, but a new inspection-error fail-open remains:

R10 — HIGH — order-read denial can still produce false clean clearance — `benchmark/bench/proc_guard.py:101-105,364-372,677-704`. Every non-ESRCH errno becomes `AccessDenied`. During cleanup, an untracked same-UID process whose order read is denied is silently ignored because uncertainty is set only for tracked PIDs. I reproduced `completed=True`, `uncertain=False`, no survivors, with the process alive.

Concrete change: map ESRCH to `NoSuchProcess`, EPERM/EACCES to `AccessDenied`, and unexpected errno such as EINVAL to `TransportAbort`. During final cleanup, inability to determine ordering for any otherwise eligible same-UID process must set `uncertain`, even when untracked. Add this counterexample as a test.

R11 — MEDIUM — router ancestry remains wall-clock ordered — `benchmark/bench/chain_ops.py:122-142,310-318`. `default_parents()` compares two `start_time()` wall timestamps. A backward step between parent and child starts makes the genuine parent appear younger, truncating the chain. Router ownership then fails closed—startup is refused and the recorded spawn is reaped—but a legitimate run can abort.

Concrete change: use `start_order()` for parent-reuse ordering, falling back to wall time only when both monotonic values are unavailable. Test both a backward-step legitimate parent and a concealed reused parent.

Technical checks:

- `ri_proc_start_abstime` and `mach_absolute_time()` are the same raw Mach tick domain on this arm64 box; direct measurement placed a spawned child’s start value between pre/post calls.
- Both exclude sleep. Ordering remains valid across sleep because both pause; slept duration is merely absent. `mach_continuous_time()` is unnecessary here.
- `rusage_info_v0` matches the SDK: 16-byte UUID plus ten `uint64_t`s; size 96, alignment 8, start offset 80, exit offset 88.
- Observed errno behavior: PID 1 → EPERM, missing/reaped PID → ESRCH, invalid flavor → EINVAL. The API supports live and zombie processes.
- Lazy ctypes initialization is thread-safe under the GIL, publishes only after full construction, and normally runs in `ProcessGuard.__init__` before the monitor starts.
- No mixed order/wall comparison occurs inside `ProcessGuard`: each comparison falls back wholly to wall time if either monotonic operand is unavailable.
- Prescribed suite: 213 passed.

not clearedThe initial errno probe hung because `proc_pid_rusage` succeeds for unreaped zombies. I stopped it and reran a bounded probe successfully; no further action is needed.

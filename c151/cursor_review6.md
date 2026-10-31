P1 — R15: answered — `benchmark/bench/proc_guard.py:519-543`; test `benchmark/bench/tests/test_c151_start_time.py:331-343`. Partial kills are recorded in `self.killed`, remaining targets are attempted, then the first `TransportAbort` is re-raised.

P2 — R16: partial — handling is correct at `benchmark/bench/proc_guard.py:581-593,684-770`, but the promised diagnostic is absent.

P3 — R17 — `benchmark/bench/proc_guard.py:774-781`: cleanup filters entries by `"identity unreadable"` but serializes only `pid/create_time`; the exception never states the reason. The test at `benchmark/bench/tests/test_c151_start_time.py:355-363` checks only generic `"cleanup uncertain"`.

P4 — R18 — HIGH — `benchmark/bench/tg1_runner.py:827-840`: the bare `guard.kill_role("grader")` can now raise before `guard.cleanup()` and status publication. An unreadable grader can survive, containers may remain, and the manifest can publish the prior discovery guard’s clean status from `benchmark/bench/tg1_runner.py:968,1233-1239`. The kill must be captured while cleanup still runs.

Caller audit:
- `run_grader()` avoids the former TransportAbort/`communicate()` hang.
- cancellation catches graceful/client/model failures and continues remaining kills.
- `verify_gone()` maps TransportAbort to unknown/false; no false-gone certification.
- cleanup and discovery context paths otherwise publish `completed=True` before propagating uncertainty.
- `chain_ops.py` has no lifecycle-method callers.
- `universe_preflight.py:67` uses cleanup through the context manager and propagates failure safely.

Focused suite: 137 passed.

not clearedNo follow-up needed; both reviews were incorporated into the verdict.

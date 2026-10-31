Focused tests: `26 passed, 167 deselected`.

T1 — partial — `benchmark/bench/tg1_runner.py:865-876`, `benchmark/m62/inject_verify.py:230-245`. Every kill is checked, null linkage fails, and continuation uses the earliest request. Linkage itself remains non-unique; see T7/T8.

T2 — answered — `benchmark/bench/proc_guard.py:394-428`, `benchmark/m62/inject_verify.py:223-235`. Tool-scoped kills are distinguished, and collateral unlinked kills fail visibly.

T3 — partial — `benchmark/bench/opencode_export.py:25-34`. Sleep no longer crosses the deadline and the first attempt retains 120 seconds, but the retry timeout can exceed the remaining deadline; see T9.

T4 — partial — `docs/specs/c147-tg1-chain-clearance.md:72,318-324`. The predicate was rewritten, but V1 still says every kind lowers exactly one constant and has an appended, hashed addendum. Alloc changes two settings and has no addendum. The earlier summary also says only “the first” kill is linked at line 39.

T5 — answered — `docs/open-questions.md:18`. The operator ruling and implemented contract are recorded.

T6 — HIGH — `benchmark/bench/tg1_runner.py:43-46`, `benchmark/bench/proc_guard.py:470-476`, `benchmark/bench/tests/test_c152_tool_scope.py:30-36`  
The registered positive is still timing-dependent. The monitor samples every 100 ms, while the retained bowling run used `python3 -m unittest bowling_test` with tests reporting 0.000–0.002 seconds. Such a child can start and exit entirely between ticks. The test presents long-lived fake processes to a synchronous tick and does not cover this race. A legitimate rerun can therefore remain `not_observed:kill`.

T7 — HIGH — `benchmark/bench/tg1_runner.py:870-875`  
The ≥6-character argv rule rejects legitimate test kills. `pytest -q` commonly becomes `[Python, /venv/bin/pytest, -q]`, with neither full path appearing in the shell command. `go test ./...` has only short launcher tokens, while the killed compiled test binary has an unrelated temporary path. Both remain unlinked and fail.

T8 — MEDIUM — `benchmark/bench/tg1_runner.py:865-875`, `benchmark/m62/inject_verify.py:233-245`  
Linkage is neither unique nor one-to-one. If one request contains multiple shell calls sharing a token such as `pytest`, the linker selects the first candidate for every matching kill. The verifier accepts duplicate `tool_call_id` mappings, so multiple kills can PASS while not being linked to their own calls, contrary to the “exactly one shell part” contract.

T9 — MEDIUM — `benchmark/bench/opencode_export.py:31-34`  
P273 can exceed its strict retry bound. With 0.6 seconds remaining after the pause, `max(1.0, …)` grants a one-second attempt. The current tests only exercise an 8.5-second remainder. A retry should not start unless at least the minimum timeout remains.

not cleared

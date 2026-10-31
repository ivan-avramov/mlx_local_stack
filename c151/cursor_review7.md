P1 — R17: partial — `benchmark/bench/proc_guard.py:775-780` serializes orphan reasons, but `unknown` entries created at `:749-750` are appended without a `reason`. The R16 test correctly asserts `"identity unreadable"` at `benchmark/bench/tests/test_c151_start_time.py:355-364`, but does not detect the reasonless duplicate entry.

P2 — R18: answered — `benchmark/bench/tg1_runner.py:827-843` catches the grader-kill failure, always runs cleanup, and records its final status. `benchmark/bench/proc_guard.py:734-783` re-audits tracked identities and fails closed on survivors or unknown state. Test: `benchmark/bench/tests/test_c151_start_time.py:367-408`.

P3 — Whole-diff pass: no new R19 finding. The bounded test-only readiness retry does not affect live tg1 behavior.

Focused suite not run.

not cleared

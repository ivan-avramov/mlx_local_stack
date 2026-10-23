F1 — OPEN (HIGH) — The committed `frozen.json` has no `production_ref`; `p426_leg.py:720-721` passes `None`, so `p426_plan.py:44-45` refuses every M1 leg before launch.

F2 — OPEN (MEDIUM) — `orchestrate.py:1220-1225` validates only ancestor PID and module name, not expected argv or creation time; a misbehaving launcher or PID-reuse race can still hide interference.

F3 — OPEN (MEDIUM) — `qualify.py:888-894` deliberately skips resolution for default `7207179b`, so existing R7 reports still record an abbreviated ref rather than the exact commit diffed; custom refs are fixed.

F4 — OPEN (MEDIUM) — The new topology tests call `ancestor_pids` and `foreign_process_problems` directly, not `preflight`, and never exercise sequencer→wrapper→qualify or report creation; the original regressions could recur while tests pass.

New findings: none.

VERDICT: DISAGREE F1 F2 F3 F4

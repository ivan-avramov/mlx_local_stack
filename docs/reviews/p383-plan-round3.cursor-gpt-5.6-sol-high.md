Reviewed `main` at `040d2836`; relevant benchmark code is unchanged from `4849a2ae`.

- R1 — CLOSED for the Round-2 requirements. §2 now covers pre-spawn, cheat, F9 accepted/exhausted, gates before salvage regardless of salvage success, and defines missing-receipt abandonment.
- R10 — CLOSED. §1 specifies strict types/ranges, finite positive `create_time`, string-only `argv`, canonical JSON, and rejection tests.
- R11 — CLOSED. §2 places the gate after hydration and before salvage and covers all requested persisted-stop kinds.
- R12 — CLOSED. §2 explicitly abandons the out-root; absence is never cleared or treated as clean.
- R13 — CLOSED. §3 makes the snapshot best-effort, distinguishes identity states, conditionally captures lineage, and reopens P388 on every recurrence.
- R14 — CLOSED. §3 removes the unsupported sample-size estimate.

R15 — BLOCKER; §1 live pre-spawn backfill / §2 P389 coverage. `accept_invocation()` changes the invocation to `hook_stopped` and persists it at `chain_core.py:1765–1769`, before `require_certain_cleanup()` at lines 1777/1782. A crash in that window leaves a non-`running` invocation. On resume, `prepare_resume()` selects only `status == "running"` records at lines 1021–1023, so neither the P389 gate nor pre-spawn backfill runs. The subsequent retry/rerun can therefore still bypass A7, and a pre-spawn incident remains without its evidence fields.

Fix: validate cleanup and backfill pre-spawn evidence before the first write that changes `running` to `hook_stopped`, making them durable in the same `chain.json` transaction. Add crash tests immediately after that write for both pre-spawn and cheat stops, asserting that evidence is already present and a failing receipt cannot launch another invocation.

No other new v3 problems found.

VERDICT: AGREE WITH CHANGES R15

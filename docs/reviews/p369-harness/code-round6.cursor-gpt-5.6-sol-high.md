# P369 phase-2 harness — Cursor gpt-5.6-sol-high CODE review round 6 (fork `p369-mtp` `db825821..d9027a60`, 2026-10-19)

Prompt: `code-round6.prompt-head.md` + the round-5 output + `git diff db825821..d9027a60` + plan v7; workspace `../mlx-vlm` at `24551869`. Attempt 1 (`--mode plan`) ended on a createPlan call with no review text; attempt 2 (`--mode ask`, stream-json) — the `result` text verbatim:

P1 — Scope verification

The checkout is still at `24551869`; `4e6d0e03..d9027a60` is empty for production `mlx_vlm` code excluding tests. The round contains two red-test/implementation pairs in the expected order. I’m now tracing the process-state and evidence-schema paths beyond the added tests, especially signal-killed workers and non-boolean evidence outside `e1c_verdict`.P1 — Verification

Read-only review of `db825821..d9027a60`; tests were not run.

- Checkout remains at `24551869`.
- `4e6d0e03..d9027a60` has no production diff under `mlx_vlm`, excluding tests.
- Both red-test commits directly precede their implementation commits.
- Changes are limited to the harness and tests.

P2 — Round-5 findings

H12 — PARTIALLY RESOLVED — MEDIUM  
`.github/workflows/tests.yml:17-18,46-49`; `mlx_vlm/tests/test_p369_phase2_oracle.py:35-44,65-70`

Problem: CI remains shallow and does not set `MLX_REQUIRE_P369_ORACLE=1`, so the history-backed oracle can skip.

Scenario: classifier logic regresses while shallow CI runs only the synthetic unit cases.

Fix: retained P394 deferral—use full history and require the oracle in its eventual gating job.

H22 — PARTIALLY RESOLVED — HIGH  
`dev/p369_phase2/orchestrate.py:930-963,1033-1056`

Observed descendants and current group members are extinguished. The disclosed spawn-and-escape-between-polls race remains: a child can call `setsid()`, lose its visible parent chain and escape before any scan records it.

Scenario: such a child survives `reap()` and overlaps a later operator run.

Fix: cooperative descendant registration or a persistent launcher/ownership mechanism; polling cannot close this race.

H23 — RESOLVED  
`dev/p369_phase2/orchestrate.py:1337-1377,1824-1858`

`Campaign(args)` no longer reads the registry or derives parameters. `prepare()` first creates the run directory, then performs those reads inside `execute()`’s persistence boundary. A signal before directory creation remains explicitly undisclosable as agreed.

H24 — PARTIALLY RESOLVED — LOW  
`mlx_vlm/tests/test_p369_phase2_orchestrate.py:899-907,964-977,1085-1095,1113-1138`; `mlx_vlm/tests/test_p369_phase2_procs.py:38-58,61-93`

Problem: children now record themselves before escaping, closing the parent-dies-before-recording hole. Teardown still trusts a bare PID without validating its recorded identity. It also waits only for file existence, although `open(..., "w")` creates the file before its PID contents are complete.

Scenario: a test observes an empty PID file and fails before registering the escaped child, or a dead child’s PID is reused and teardown signals an unrelated process.

Fix: publish PID plus start identity atomically, wait for a complete parseable record, and revalidate that identity before teardown signals it.

H27 — RESOLVED  
`dev/p369_phase2/orchestrate.py:817-835,1158-1196`

TERM/INT during launch and tracker publication is deferred without changing the inherited signal mask. The worker is owned before the interruption is propagated, and cleanup runs under signal deferral.

H29 — RESOLVED  
`dev/p369_phase2/orchestrate.py:1033-1056`

Tracked identities are repeatedly rescanned and signalled. Success is returned only after no owned live process remains, and each scan is bounded by the cleanup deadline plus margin. The separate unverifiable-`ps` orphan path is H37.

H30 — RESOLVED  
`dev/p369_phase2/orchestrate.py:913-975,1083-1087,1183-1213`

Normal exit is observed as an unreaped zombie; no `Popen.poll()` occurs before verified cleanup. The root identity anchors group discovery until `reap()` proves extinction and calls `wait()`. A signal-killed worker receives a negative return code and is rejected even if it wrote `result.json`.

H31 — RESOLVED  
`dev/p369_phase2/orchestrate.py:1078-1087,1158-1174`

Tracker creation failure now propagates as unknown process state. It can no longer become an ordinary untracked `exited` outcome or admit a result.

H32 — PARTIALLY RESOLVED — MEDIUM  
`dev/p369_phase2/orchestrate.py:1024-1030,1183-1196`

Problem: second signals during `stop_worker()` and normal `reap()` are correctly replayed after extinction. Exception cleanup defers further signals and preserves the primary exception only when `_stop()` succeeds. If `_stop()` itself raises, that cleanup exception replaces the primary interruption/error.

Scenario: SIGTERM triggers cleanup, then `ps` fails. The run is recorded as `HARNESS_ERROR` from cleanup instead of propagating the primary interruption.

Fix: capture the primary exception and cleanup failure separately, persist both, and propagate the primary as specified after cleanup terminates.

H33 — RESOLVED  
`dev/p369_phase2/orchestrate.py:838-887,1033-1056`

`ps_table()` caps attempt timeouts and backoff against a monotonic deadline. `reap()` supplies its deadline plus the documented five-second margin.

H34 — PARTIALLY RESOLVED — HIGH  
`dev/p369_phase2/orchestrate.py:593-600,494-496,525-535,1570-1580,1677-1681`

Problem: same-instance E1c rows, states and kernel verdicts now require exact booleans. Other comparator/kernel evidence still uses truthiness:

- C1 uses `bool(on["c1"]["acceptance"]["pass"])`.
- C2 combines truthy `rows.pass` and `states.pass`.
- E2 accepts truthy kernel `pass`.
- E7a/E7b accept truthy kernel and continuity values.

Scenario: a schema regression emits `"false"`. C1, E2 and E7a treat it as true, permitting a full PASS without established control, kernel or incidence evidence. Falsy malformed values become experimental `INCOMPLETE`/invalid findings rather than `HARNESS_ERROR`.

Fix: validate every evidence `pass`/continuity field with `type(value) is bool` at artifact ingestion; malformed evidence must raise.

P3 — New findings

H35 — HIGH — `dev/p369_phase2/orchestrate.py:1083-1098,1207-1214`; `dev/p369_phase2/worker.py:117-128,678-694`

Problem: `supervise()` checks for a zombie before evaluating campaign, job or current-request deadlines. Exit therefore wins over an already-expired watchdog.

Scenario: a request finishes after its deadline, writes a successful result and exits before the next poll. The supervisor sees the zombie, reports ordinary exit, and `run_job()` accepts the result. The run can PASS despite the plan requiring every timeout to be censored or fail.

Fix: persist request and job completion timestamps and compare them with their applicable deadlines before accepting exit. Conservatively give an expired deadline precedence where no durable completion timestamp exists.

H36 — HIGH — `dev/p369_phase2/orchestrate.py:1998-2003`

Problem: the externally loaded smoke summary is authorized through truthiness rather than exact booleans or validated smoke evidence.

Scenario: a malformed summary containing `"pass_": "false"` and `"fits": "false"` authorizes the full run because both strings are truthy. The full campaign can then PASS without the smoke positives, runtime inventory or E7b smoke requirement having passed.

Fix: require exact `True` booleans, `status == "SMOKE_PASS"`, and validate/recompute the per-pick smoke gate from the bound summary evidence.

H37 — HIGH — `dev/p369_phase2/orchestrate.py:986-997,1018-1020,1046-1051`

Problem: when `ps` becomes unverifiable, `_kill_unverified()` kills only the original process group and leader. Already tracked descendants that called `setsid()` are outside that group and are neither signalled nor awaited.

Scenario: the tracker records an escaped GPU helper, then all `ps` retries fail during cleanup. The harness aborts, but the helper survives as an orphan and can consume GPU resources after the campaign exits.

Fix: retain an ownership mechanism that remains usable when global `ps` fails—such as cooperative PID/start registration through a persistent launcher—and do not finish cleanup until those identities are verified extinct or explicitly surfaced for operator remediation.

H38 — MEDIUM — `dev/p369_phase2/orchestrate.py:1907-1915`; `mlx_vlm/tests/test_p369_phase2_orchestrate.py:1278-1285`

Problem: the new smoke E7b gate accepts any truthy `sessions` object plus either status label. It does not establish that exactly one expected session ran or that the report has a valid session schema.

Scenario: an E7b aggregation regression returns `sessions=[{}], status="INCOMPLETE"`. The smoke passes even though no named session or continuity/censoring report was established; the new test explicitly accepts this minimal shape.

Fix: require exactly the selected first C84 session, validate its name and censoring/report fields with exact types, and derive the aggregate status from that validated session. Continuity can remain non-gating.

P4 — Claim integrity

H34, H35 and H36 still permit PASS without establishing required evidence. H34 can also classify malformed harness evidence as an MTP outcome. H37 can leave an orphan process after failed cleanup. The E7b policy itself is correctly narrowed—descriptive in the full run and attempted once in smoke—but H38 does not prove the smoke report’s structure.

VERDICT: NOT CLEARED H34 H35 H36 H37

---

## Closure (lead, 2026-10-19, session 3) — the harness review is CLOSED (C186; no further round)

Operator ruling on the round-6 escalation (C186): fix H34, H36, H38; accept H35; record H37 as a residual.

- **H34 — FIXED** (fork `p369-mtp`: red `5157af6a`, green `508bab78`).
  `exact_bool` raises `MalformedEvidence` (a harness error → `HARNESS_ERROR`, never an MTP outcome) at every evidence site:
  `pick_outcome` (every cell's `c1.identical` / `neutral` / `evidence_ok` / `pass_` / `c2.identical` validated before any
  decides), `e1c_verdict` (comparator rows / states / kernel + the per-query straddle), `e1c()` (cell straddle, C1
  acceptance, C2 rows + states), `e2()` kernel verdicts, `e7a_stats` / `e7b_session` kernel verdicts, every E7b follow-up
  continuity record (a missing record is malformed: the worker writes one for every turn > 0), `e7b_status`, and the
  smoke gate in `overall_status`.
- **H36 — FIXED.** `main` authorizes a full run only through `smoke_authorization_problems`: phase smoke, status
  `SMOKE_PASS` with exit code 0, exact `True` for `pass_` and `fits`, and the stored gate EQUAL to `smoke_gate()`
  recomputed from the summary's own evidence (`smoke_gate` is now a pure module function; the binding check is unchanged).
- **H38 — FIXED.** The smoke gate requires EXACTLY one E7b session named after the first reconstructed C84 item; the
  session is exactly a timeout censor `{name, censored: true, reason: "timeout"}` or a typed `e7b_session` record
  (`censored` agrees with `reason`), and the report's status is re-derived via `e7b_status`. Continuity stays descriptive.
- **H35 — ACCEPTED (operator).** A request that completed and wrote its result before the supervisor's next poll is a
  valid observation; the per-request watchdog exists to stop requests that cannot converge or have wedged, not to censor
  a finished one.
- **H37 — RESIDUAL (operator), disclosed.** If `ps` fails completely after a tracked descendant has called `setsid()`,
  `_kill_unverified` SIGKILLs only the worker's own group and the worker; the escaped helper may survive. The harness
  still fails closed (it raises; extinction is never claimed). The operator verifies the box after any such abort.
- **Found while closing — P396 (lead call), FIXED.** The `ignore-term` supervise test flaked (≈ 4 / 15): `_stop()`'s grace
  loop limited each `ps` scan to the grace end alone, so the last scan ran `ps` with a few ms left, timed out, and a
  TERM-ignoring worker became a harness error instead of reaching the SIGKILL reap. Fix: the scan keeps `PS_MARGIN_S`
  past the grace end (as `reap()`'s do). Deterministic red test (ps modelled as needing ≥ 0.3 s) `fc2dbb7e`, fix `59b32042`.

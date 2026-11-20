## Round 3 (final verify) — GLM

I read the v1.2 spec, the `spec-v1.1-to-v1.2.diff`, the R2 ledger, my own R2 findings (`your-r2-verify-glm.md`), and C372 in `docs/open-questions.md`. Read-only; no files modified.

### Disposition of my round-2 findings

**F1 (§4.3 loop descendant check) — RESOLVED.** Unchanged in v1.2; §4.3 still lists the model-role `sleep 600` descendant kill under "Unchanged checks stay" and the `PASS_NO_INFLIGHT` branch is conjunctive on `in_flight_at_kill == 0` / `requests_started` unchanged / `after.in_flight == 0` / `trailing` non-interrupted, so it cannot bypass the descendant kill.

**F2 (reconciliation failure too broad) — RESOLVED.** §5.1's PRE-outcome list is grader/hook infra + uncertain-cleanup-proven-certain only; §5.2 routes a reconciliation failure surviving §4 to POST-outcome `accounting_fault` (no rerun); §5.5 adds the unexplained worker/receipt/session-backend inconsistency to integrity; §5.9 closes the accounting-vs-integrity table.

**F3 (PAUSED leg state) — RESOLVED.** §5.6 adds `PAUSED` to `LEG_STATES`, `classify_leg`, the harvest rule table; §8.3 renumbers PAUSED to §5.4 / §5.6.

**F4 (chain_rows SLOT_DISPOSITIONS / slot_table) — RESOLVED.** §5.7 names `SLOT_DISPOSITIONS` gaining `harness_fault` with a `slot_table` branch queuing `(slot, 1)` (P426 has no cheat rerun), plus `pump_barrier`, `run_p426_leg`, `ready.json`/`items/<slot>` keying, `check_p426_ledger`, and the consumer rule.

**F5 (step-offset proof / buffered stdio) — RESOLVED.** §4.1–4.2 keep the conjunctive gate (`|C|==n==expected+1` AND positional pairing AND n-th END offset `> ingested_offset_at_count` AND worker deltas hold), the trailing-`STREAM_CLOSED` variant, and the `no_signal` order field; the worker-delta conjunct defends the buffered-stdio false-pass; §10.2 keeps the real-path sgf-parsing check.

**F6 (env-based attribution denied read) — RESOLVED.** §3.2 now covers *any* denied read (start order, liveness, cwd, environ) on a process (a)/(b) do not claim → `foreign_new unreadable`; only a process already claimed by (a)/(b), or an unreadable session id, → `uncertain`; and "the ownership tests run before any read that can mark a process unreadable."

**F7 (HOLD vs outer Sequencer.supervise) — RESOLVED.** Unchanged in v1.2; §8.2 still names `Sequencer.supervise` subtracting the held interval and the resume re-checks.

**S1 (escaped setsid residual) — RESOLVED (operator-confirmed).** §3.7 records it as `foreign_new`, not killed; C372 accepts it.

**N1 (§12 literal paths) — RESOLVED.** §12 now pins `PROTECTED_PUSH_PATHS` as a constant in `local_gate.py` with the four repo-relative literals (`benchmark/opencode_bench_v2_web_tg1.json`, `benchmark/opencode_plugins/{noretry,toolbounds,datefreeze}.js`), so a future move is a visible spec/constant change rather than a silent empty-diff pass.

**N2 (§12 rewind / missing-`pushed_base`-object) — RESOLVED.** §12 now states "the commit must exist in the repo (else refuse)" and "any git error refuses; a refusal prints a regate hint," and adds red tests for `pushed_base` absent from the repo and a non-`main` pushed ref at level `full`. Fail-closed is now explicit.

### Anything else the diff breaks or leaves failing

One minor observation, not a defect:

§5.7 drops the v1.1 clause "fault-then-cheat and cheat-then-fault each consume their own cap" and replaces it with "P426 legs have no cheat rerun ... so a P426 slot's rerun index is 0 or 1" and "`MAX_RERUNS` / `exhausted` unchanged for per-arm legs." For P426 this is unambiguous. For per-arm legs, the harness-fault rerun cap (§5.6 "1 rerun per item") and the cheat rerun cap (`MAX_RERUNS`) are still stated separately but v1.2 no longer says explicitly that they are *independently* consumed. The natural reading (two distinct caps named in two distinct clauses) is the intended one and matches v1.1's removed clarification, so this is a literal-spec sharpness gap without material consequence, not a defect. If the implementer wanted it airtight, one clause ("the harness-fault rerun cap and the cheat rerun cap are independently consumed") would close it.

No blocker, major, or minor defect remains; the diff does not break any prior provision.

NOTHING OF SUBSTANCE

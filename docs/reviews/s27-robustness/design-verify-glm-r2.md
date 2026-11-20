## Round 2 (verify) — GLM

I read the diff, the R1 ledger, my own r1 opinion (`your-r1-opinion-glm.md`), C371/C372 in `docs/open-questions.md`, and the new §12 against `benchmark/bench/local_gate.py`.

### Disposition of my round-1 findings

**F1 (§4.3 loop descendant check) — RESOLVED.** §4.3 now lists "for loop the model-role `sleep 600` descendant kill" under "Unchanged checks stay", and the `PASS_NO_INFLIGHT` branch only relaxes the in-flight link (its own conjunctive conditions: `in_flight_at_kill == 0`, worker `requests_started` unchanged, `after.in_flight == 0`, `trailing` not an interrupted kind). The descendant kill cannot be skipped by the no-inflight short-circuit.

**F2 (reconciliation failure too broad) — RESOLVED.** §5.1's PRE-outcome harness-fault list no longer contains reconciliation failure; it is grader/hook infrastructure + uncertain-cleanup-proven-certain only. §5.2 makes a reconciliation failure that survives §4 a POST-outcome `accounting_fault` with no rerun. §5.4 adds "an unexplained worker / receipt / session-backend inconsistency that is not the item's own accounting" to integrity. This is stricter than my proposal — outcome-correlated reconciliation failures never rerun.

**F3 (PAUSED leg state) — RESOLVED.** §5.6 adds `PAUSED` to `LEG_STATES`, `classify_leg`, and the harvest rule table; §8.3 lists "PAUSED = §5.3 / §5.5". A paused leg is resumed/archived by the designer, never harvested.

**F4 (chain_rows SLOT_DISPOSITIONS / slot_table) — RESOLVED.** §5.6 names `chain_rows.SLOT_DISPOSITIONS` gaining `harness_fault` with a `slot_table` branch queuing `(slot, rerun_index + 1)`, separate from `MAX_RERUNS`/`cheat`, plus `pump_barrier`, `run_p426_leg`, `ready.json`/`items/<slot>` keying, `check_p426_ledger`, and the consumer rule.

**F5 (step-offset proof / buffered stdio) — RESOLVED (in substance).** §4.1–4.2 make the late-record gate conjunctive: `|C|==n==expected+1` AND positional pairing AND n-th END offset `> events_size_at_count` AND worker deltas hold, plus the trailing-failed variant (`STREAM_CLOSED`, `|S|==|C|+1`) and the `no_signal` order field. The buffered-stdio false-pass I worried about is now defended by the worker-delta condition (a phantom flush with no worker completion fails the deltas), and §10.2 adds the real-path sgf-parsing events check. The spec does not literally say the offset is "secondary", but the conjunction makes it so.

**F6 (env-based attribution denied read) — RESOLVED.** §3.2: a denied cwd/environ read on a process (a) and (b) do not claim → `foreign_new` with `unreadable: true` (never `uncertain`); only a process already claimed by (a) or (b) whose read fails → `uncertain`. This matches my proposal.

**F7 (HOLD vs outer Sequencer.supervise) — RESOLVED.** §8.2 names `Sequencer.supervise` as a changed site that "reads the open episode and subtracts it" from the deadline, and adds the resume re-checks (worker identity, `:8000` owner, AC power, no other GPU job, cache-session state).

**S1 (escaped setsid residual) — RESOLVED (operator-confirmed).** §3.7 records it as `foreign_new`, not killed, with the next item's clean-tree / protected-path checks catching its effects; C372 accepts it.

### New §12 (push binding) review

§12 is sound against the existing `local_gate.py`: `run` already writes `receipt["pushed_base"]` for stack (line 512), `check_lines` fetches `<remote>` before calling `push_level` (line 759), and `push_level` is the right site for a stack-only `full`-level guard. Two minor notes:

**N1 — §12, "the four protected paths"**
Severity: minor (hypothesis). The spec names them descriptively ("the tg1 carrier JSON, `noretry.js`, `toolbounds.js`, `datefreeze.js`") without repo-relative paths. The concrete targets are unambiguous in this tree (`benchmark/opencode_bench_v2_web_tg1.json`, `benchmark/opencode_plugins/{noretry,toolbounds,datefreeze}.js`), but a future rename/move of the carrier would silently make the binding check a non-existent path — `git diff -- <missing path>` exits 0 with empty output, so the binding would accept without actually checking. Scenario: the carrier JSON is later moved; the binding still passes every push. Proposed change: pin the four paths as literals in §12 (or name the constant the implementer defines), so a move is a visible spec change.

**N2 — §12, the rewind / missing-`pushed_base`-object case**
Severity: minor (hypothesis). The red tests cover fast-forward moves of `remote/main`. If `remote/main` is rewound (force-push) between gate-run and push, `pushed_base` may not be reachable from the fetched `<remote>/main`, so `git diff <pushed_base> <remote>/main` errors on an absent object. The spec does not state the behavior. The natural implementation is fail-closed (refuse with a regate hint), which is safe; but it is unstated. Proposed change: add "if `pushed_base` is not a commit in `repo_dir` after the fetch, refuse with a regate hint" so the implementer does not accidentally treat the git error as a pass.

### Anything else the diff breaks or leaves failing

Nothing else. The §5.5 "1 rerun per item" vs §5.6 "fault-then-cheat and cheat-then-fault each consume their own cap" phrasing is slightly ambiguous (total vs per-kind cap), but §5.6's clarification ("separate from `MAX_RERUNS` / `cheat`") resolves it: the fault-rerun cap is 1 per item, the cheat-rerun cap is `MAX_RERUNS`, independently consumed. Not a defect.

NOTHING OF SUBSTANCE

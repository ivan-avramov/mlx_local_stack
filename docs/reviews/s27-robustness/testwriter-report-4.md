# Test-writer report, delivery 4: S27 bundle, fix round 2 (candidate 3)

**Verdict: merge.** Y1, Y3 and Y4 are resolved, with scenario tests that fail on the inspected candidate-2 behaviour. My whole set (288) and `test_s27_impl_*` (245) pass on candidate 3. I have two minor remarks and one limit on what I reviewed (section 4).

## 1. The conflicting v3 test, re-staged

`test_s27_fe_r1.py::test_x10_a_session_member_started_after_the_probe_is_ours_and_is_killed` expected a live session leader whose start differed from the recorded probe start to be killed. Y3 rules that case a reused session, so the old test could not hold. It is replaced by three real-process tests:

| test | class | what it states | baseline | cand. 3 |
|---|---|---|---|---|
| `test_x10_a_non_leader_member_of_the_probes_session_started_after_it_is_ours_and_is_killed` | (b) | the stand-in probe is a session leader started with `start_new_session`; it starts a non-leader member; `not_before` is the probe's own start → `session_reused` is None, the member is killed and verified gone | fail | pass |
| `test_x10_a_member_of_the_probes_session_is_still_ours_when_the_probe_has_already_exited` | (b) | same, with the leader already gone (the session outlives its leader) → the member is killed | fail | pass |
| `test_x10_a_live_session_leader_that_is_not_the_recorded_probe_is_a_reused_session_and_nothing_is_killed` | (a) | the leader of `sid` is alive but its start is not the recorded one → no session claim, `session_reused.pid` is the leader, `killed == []`, leader and member both still alive; candidate 2 claimed and killed them (inspection of the Y3 description and `chain_ops.owned_scan` before the guard at lines 1003-1016) | fail | pass |

The kept tests `test_x10_a_session_member_older_than_the_probe_is_not_ours` and `test_x10_without_the_probes_recorded_start_a_session_proves_nothing` still pass.

## 2. New tests (`test_s27_fe_r2.py`, 17 tests)

I read `test_s27_impl_r2fix.py` first. The implementer's file already covers Y1's five bad samples, Y2, Y3's guard branches, Y4's seven non-binding variants, Y5, Y6 and the faulted-interim-boundary clarification. I added only what it does not:

| id | tests | class | baseline | cand. 3 |
|---|---|---|---|---|
| Y1 | the anchored case still holds for a sample that read integer 0 (control); an absent / `None` / `False` / `True` / `"0"` / `""` / `0.0` / `[]` / `{}` / `-1` sample (×10) is refused and never takes the `open_step_at_signal` shape. This widens the implementer's five values to ten, including `True`, `""`, containers and a negative | (b), (a) | not collectable on the baseline (the file imports the candidate's helper) | pass |
| Y4 | a bound sidecar is accepted by freeze and by harvest (control); freeze AND harvest refuse: a field changed after sealing, a changed row digest, a missing sidecar for a slot the ledger flags, a sidecar that is a symlink to a valid copy; another slot's sealed sidecar copied onto this slot's path is refused | (a), (b) | not collectable | pass |

Note on the baseline: `test_s27_fe_r2.py` imports `acct_leg` from the implementer's `test_s27_impl_r2fix.py`, so it cannot be collected on the baseline copy ("1 error during collection"). The other ten files give **157 failed, 114 passed** on the baseline.

## 3. Runs

All through `../fe_test.sh stack …`.

| run | result |
|---|---|
| my whole set on candidate 3 (11 files: reconcile, ownership, offsets, positives, done_hook, chain, grader, harvest_view, push_binding, r1, r2) | **288 passed** |
| the same set minus r2, on the baseline copy | 157 failed, 114 passed |
| `test_s27_impl_*` on candidate 3 | **245 passed** |
| `test_s27_fe_r1.py` + `test_s27_fe_r2.py` on candidate 3, run alone | 72 passed |

No failures to quote verbatim. The one error is the baseline collection error above.

## 4. Review of fix 2 against Y1–Y6

| id | verdict | evidence |
|---|---|---|
| Y1 | resolved | `_open_step_at_signal` now requires `type(sample) is int` and equal to 0; my ten-value test passes, so no malformed sample enters the anchored case |
| Y2 | resolved per the implementer's tests; I did not add one | the typed spawn / transport faults and the tri-state OOM inspection have their own tests in `test_s27_impl_r2fix.py`, which pass; I did not read the `proc_guard.container_oom` and `parse_go` diffs line by line |
| Y3 | resolved | `owned_scan` reads the live pid == `sid` process before claiming members; a different start means no claim and a `session_reused` record; an exited leader still claims members bounded by the probe start; an unreadable leader leaves the scan uncertain with no claim; my three real-process tests and the implementer's three pass |
| Y4 | resolved | one validator, `p426_hooks.accounting_problems`, is used by the chain, freeze and harvest; my refusals (tampered, missing, symlinked, wrong slot) hold for both consumers and the bound control is accepted |
| Y5 | resolved per the implementer's tests | the helper plus a source check; I did not trace it |
| Y6 | resolved per the implementer's tests | `foreign_new` basename and the chain scan's `path_only` basename are both capped at 64 characters |

Findings:

1. **Minor, design note, `p426_hooks.accounting_problems` (lines 113-116).** A sidecar naming no item record is accepted whenever chain.json recorded any done-step failure for that slot attempt. Every accounting fault the chain handles is recorded in `p426_accounting`, so for chain-produced data the clause is always true. It therefore does not separate "the hook failed before writing a record" from "a record exists but the sidecar does not name it". The binding that protects the data (slot, attempt, row, disposition, seal) is unaffected, and freeze and harvest still refuse the unrecorded, forged case. The protection is only as strong as chain.json, which every consumer already trusts. I did not write a failing test for it, since it follows the implementer's stated choice 5.
2. **Minor, `chain_ops.owned_scan` (line 1014).** The reuse test compares the leader's start with `not_before` by float equality. Both come from the same `start_time` reader and survive JSON unchanged, so it holds today. If a later change rounds or scrubs numbers in the manifest, every probe would be taken for a reused session and its session would never be claimed. That fails closed (a scan that proves less), not open.
3. **Limit of this review.** I traced Y1, Y3 and Y4 in the source and tested them. For Y2, Y5, Y6 and the faulted-interim-boundary clarification I relied on the implementer's report and tests, which pass.

Nothing was committed, pushed, reset or reverted; no environment variables or credentials were read or printed.

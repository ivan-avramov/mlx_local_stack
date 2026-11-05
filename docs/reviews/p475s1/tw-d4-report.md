# Test-writer delivery 4: P475 stage 1, final candidate (`candidate-fix2.diff`)

**Verdict: merge.** The new tests for vP1, vP3 and vP4 pass on `candidate-fix2` and fail on `candidate-fix`. No new candidate defect found.

## Results on `candidate-fix2.diff`

- **Frozen directory (`bench/tests/p475s1`):** `537 passed in 86.71s (0:01:26)`. That is the earlier 513 plus 24 new tests in `test_v14_fixes.py`. None of the earlier frozen tests changed.
- **Implementer suites (`test_p475_impl_*.py`):** `273 passed in 21.51s`.
- **Touched suites** (`test_run_capacity`, `test_capacity_*`, `bench_watch`, `chain_ops` and `p426_*` files): `557 passed in 33.02s`.

The swap was done with `git apply -R` of `candidate-fix.diff` and then applying `candidate-fix2.diff`. I confirmed it by finding the new `valid_inventory` code in `bench/p475_kv.py`.

I could not do the `diff -r` check of the frozen directory against `.p475-material/frozen-tests-d3`, because that path is not in the copy. The fix report says it checked this itself.

## New tests (`test_v14_fixes.py`)

I ran every new test on both candidates. On `candidate-fix.diff`: `17 failed, 7 passed`. On `candidate-fix2.diff`: `24 passed`.

| Finding | Tests | On `candidate-fix` |
|---|---|---|
| **vP1**, replay | An N16 smoke leg whose harvest was refused, then its watcher journal or capacity manifest deleted: the replay must not publish (`run` nonzero, no dossier, no `.stage`, `LAST_LEG_END` untouched). | red ×2 |
| **vP1**, forged exception | A receipt that says "no watcher report" but is still speed-valid, with the journal deleted, must not be published. | red |
| **vP1**, load | Each of the five inventory files is missing from the dossier and from `SCRUB_MANIFEST.json`, or only omitted from the manifest. The table must be PARTIAL and nonzero. | red ×4 (missing; the ladder-missing case was already refused) and red ×5 (manifest omits) |
| **vP1**, forged exception at load | Forged "no watcher report" on a speed-valid dossier. | red |
| **vP3** | A stale b4 dossier in a two-block run; a b3 dossier when no deciding block was started; a b4 dossier beside the recorded b3 (b3's `29.6` stays shown, table PARTIAL). | red ×3 |
| **vP4** | After `--max-deciding 0`, standalone `matrix` through `main([... "matrix"])` returns nonzero. The canonical file is still written and labelled `UNRESOLVED`. | red |

The 7 that pass on both are invariants:
- a watcher that wrote nothing is still a replaceable speed-invalid leg, and its dossier is never used;
- the missing-ladder case;
- the recorded deciding block alone is accepted;
- standalone `matrix` returns 0 for a settled run and for a stable run;
- the two fixture-health checks.

The designer's reading of vP1 holds in the tests. A journal may be absent only when the receipt records "no watcher report" and the leg is not speed-valid. A forged excuse on a speed-valid receipt is refused, both at replay and at load. The watcher-wrote-nothing leg is harvested, replaced by `.a2`, and the matrix lists it as replaced and not as used.

## vP2: inspection only

`RealOps.spawn` internals aren't reachable through the Ops seam, so I did not test it. I read `p475_kv.py:1984-2038`:
- `Popen` runs inside `try/finally`, so the log file is closed even when `Popen` fails.
- The process group is captured as `p.pid` only when a new session was requested, and is `None` otherwise, so the caller's own group is never signalled.
- If the create-time capture raises, `_kill_spawned` sends TERM, then KILL, reaps the leader, and polls `group_alive` until the group is empty. It stops as soon as both the leader and the group are gone, and the original error is re-raised.
- A cleanup failure never replaces the triggering error.

The logic is sound. The implementer's hermetic fake-`Popen` tests cover it; I did not run them separately beyond the 273 above. The router half is untouched, as scoped.

## Findings and observations

No candidate defects.
- **O1 (the fix report's P2):** with `state.json` gone, no deciding block is recorded, so regenerating the matrix from dossiers alone refuses any deciding-block dossier. This is fail-closed. It is a new behaviour, but it matches the contract's wording that deciding data comes only from the recorded identity.
- **O2:** carried over from earlier deliveries:
  - speed-invalid smoke legs are re-attempted without a cap;
  - the NOT_STARTED cap is one counter for the whole run;
  - `RealOps.group_alive` and the telemetry identities are live-only.

No contract deviations beyond those already listed.

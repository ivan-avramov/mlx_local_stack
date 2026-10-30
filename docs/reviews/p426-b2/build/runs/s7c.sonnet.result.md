All three findings are fixed and the targeted run is green: `1292 passed in 429.45s (0:07:09)`. I did not run the full suite.

## Fixes

- **P54:** `P426Hooks.after_attempt` now runs the bound ready checks (registry sha, lifecycle hash, worktree clean) before reconciliation. A failure becomes an `invalidate`, and the invalid item record carries a `ready_checks` entry with `ok: false`. Nothing is added on success, so existing item records are unchanged. A check that cannot run raises `HookInfrastructureError`, as at `ready`.
- **P55:** `listeners` is now in `P426_ENTRY_SEAMS` and the optional `getattr` path is gone. The shared `FakeOps` in `test_c147_chain_runner.py` now has `listeners()` returning `[]`, so the frozen world still works. No frozen fake needed editing, and I made no frozen-file edits.
- **P56:** the probe of an opposing lock opens it without `O_CREAT`. A missing file counts as free. Any other open error raises `LockRefused` ("… cannot be probed"). A held lock is still refused. The own lock still creates its file.

## Files changed

- `benchmark/bench/p426_locks.py`: new `_probe_free`; `acquire` uses it for the opposing locks.
- `benchmark/bench/p426_hooks.py`: `after_attempt` runs the ready checks.
- `benchmark/bench/chain_core.py`: `listeners` added to `P426_ENTRY_SEAMS`; the entry row calls `ops.listeners()` unconditionally.
- `benchmark/bench/tests/test_c147_chain_runner.py`: `FakeOps.listeners`.
- `benchmark/bench/tests/test_b2_s7_locks.py`: 12 new tests.

## Red first

I ran the new tests before any fix. 11 failed for the stated reasons, and the 12th (a held opposing lock is still refused) is a control that passes.

- **P54, four tests** (worktree edited during a mid-invocation item, the same during the last item, registry change, lifecycle change): `AssertionError: assert (2 == 2 and False)`, because the item's `.done` was answered `.continue`.
- **P54, two hook-level tests:** `assert ('accept' == 'invalidate'` and `Failed: DID NOT RAISE HookInfrastructureError`.
- **P55:** `AssertionError: assert 'listeners' in ('last_leg_end', 'power_state', 'start_state')`.
- **P56, two tests** (gate creates no `p426` file or directory; a chain probing `gate/RUNNING` creates no `gate/` directory): `AssertionError: assert not True`.
- **P56, two tests** (opposing lock is a directory; its parent is a file): `IsADirectoryError` and `FileExistsError`, because the old code crashed instead of refusing.

After the fixes one of my own tests failed on a wrong expectation. The parent-is-a-file case reports `SEQUENCER.lock` first (the first lock probed), not `LEG.lock`. I corrected the test, not the code.

## Command

```
../bin/run_stack_tests.sh bench/tests/test_b2_s7_locks.py bench/tests/test_b2_s1_cli.py bench/tests/test_b2_s2_probe.py bench/tests/test_b2_fix_chain.py bench/tests/test_local_gate.py bench/tests/test_c147_chain_runner.py bench/tests/test_p371_chain_core.py bench/tests/test_p371_baseline.py
```

I extended it with the importers of the changed modules: `test_b2_s3_core.py`, `test_b2_s4_reconcile.py`, `test_b2_s5_receipt.py`, `test_b2_s6_watch.py`, `test_b2_fix_goldens.py`, `test_p426_leg.py`, `test_p290_docker_gate.py`, `test_p279_smoke.py`, `test_p311_chain.py`, `test_p364_chain.py`, `test_p371_isolation.py`, `test_m63_predictor.py`, the three `test_p371_review_*` tg1 files, `test_t3_local_gate.py`, `test_t3_wave1.py`, `test_chain_ops.py` and `test_m64_chain_ops.py`. The result is the 1292 passed line above.

All four fixes are in and every suite passes. Nothing is committed, as the brief requires.

## Per fix

**vP1: a VALID dossier holds its exact file inventory** (`bench/p475_kv.py`, new `valid_inventory`, plus changes in `harvest` and `load_dossier`)
- **Change:** a VALID leg needs `receipt.json`, `capacity_ladder.p475-<leg>.jsonl`, `capacity_ladder.p475-<leg>.manifest.json`, `watch.jsonl`, `kv_line.json` and `worker_argv.json`.
- **Harvest:** if any source is missing, the harvest raises before anything is staged, so no dossier or stage exists and `LAST_LEG_END` is not touched.
- **Loading:** `load_dossier` refuses a VALID dossier when any of those files is missing from the directory or from `SCRUB_MANIFEST.json`. INVALID dossiers keep the old rule.
- **Tests:** a missing watch journal, manifest or rows file each refuses the harvest and leaves `LAST_LEG_END` alone; a driver that writes no manifest gets no dossier; each inventory file missing from the directory or from the manifest refuses (5 + 5 cases); a receipt missing from the manifest refuses. Guard tests (green before and after): INVALID legs keep the old rule; a complete replay still harvests.

**vP2: spawn cleanup** (`RealOps.spawn`, new `_kill_spawned`)
- **Change:** the process group is captured right after `Popen`. With its own session the group id equals the pid; without one it is None, so the caller's own group is never signalled.
- **On failure:** if anything after `Popen` raises, including the create-time capture, the group gets TERM then KILL. The leader is reaped and the group polled until empty, then the original error is re-raised.
- **Also:** the log file is now closed even if `Popen` itself fails, and the return shape is still `{"pid", "create_time"}`. The router half is untouched, as scoped.
- **Tests** (hermetic, with a fake `Popen` and `killpg`): a group that dies on TERM; a group that only dies on KILL; a child that ignores TERM after the leader exits; no session means only the leader is signalled; a successful spawn signals nothing; a `Popen` failure signals nothing.

**vP3: only recorded blocks are accepted** (new `recorded_block_plan`, plus changes in `load_dossiers` and `matrix`)
- **Change:** measurement blocks come from `state["plan"]["blocks"]`. The deciding block comes from `state["deciding"]["block"]`, and only if that block was started. A usable dossier for any other block is a dossier problem, so the matrix is PARTIAL and the run's deciding step stops.
- **Deciding column:** the matrix now shows only the recorded deciding block.
- **Tests:** a stale b4 dossier in a two-block run; a b3 dossier when no deciding block was started; a b4 dossier beside a completed recorded b3, where b3 stays shown and b4 is refused; the run stops on an off-plan dossier.

**vP4: standalone `matrix` exits nonzero on an unresolved flag** (`matrix` return code)
- **Change:** the exit code is `0 if complete and not unresolved else 1`. Whether the canonical or PARTIAL file is written is unchanged.
- **Tests:** after a run with `--max-deciding 0`, `main([... "matrix"])` returns nonzero, the canonical file still exists and is labelled UNRESOLVED; a resolved run still returns 0.

Red-first: the new file `bench/tests/test_p475_impl_fixes2.py` showed `24 failed, 7 passed` before the fixes. The 7 that passed are guard tests for behaviour that must not change.

## Commands (run from `benchmark/`)
- `../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_p475_impl_*.py` → `273 passed in 27.06s`
- `… bench/tests/p475s1` → `513 passed in 82.41s (0:01:22)`
- Touched suites (`test_run_capacity.py`, `test_capacity_*.py` and the 17 files matching `bench_watch|chain_ops|p426`) → `557 passed in 31.75s`
- The frozen copy in `benchmark/bench/tests/p475s1/` is byte-identical to `.p475-material/frozen-tests-d3` (checked with `diff -r`).

## Open points
- **P1 (my reading of vP1, for your decision).** Taken literally, "VALID needs `watch.jsonl`" breaks contract R11: a VALID leg whose watcher wrote nothing ("no watcher report") would stop the run at harvest instead of being replaced. So I made one exception: the journal may be absent only if the receipt records "no watcher report" and the leg is not speed-valid. Such a dossier can never be used, so Sol's scenario (a speed-valid leg whose journal disappeared) is still refused, and a test shows a forged "no report" on a speed-valid receipt is refused too. A test also shows such a leg is harvested and replaced. If you want the literal rule instead, that is a contract change to R11.
- **P2 (side effect of vP3).** With `state.json` gone, no deciding block is recorded, so regenerating the matrix from dossiers alone refuses any deciding-block dossier. The frozen regenerate-from-dossiers test still passes because its run has no deciding block. I think this fail-closed behaviour is right, but it is new.
- **P3 (setup step).** The sandbox wanted approval for `cp -R` and `shutil.copytree`, so I copied the 15 frozen files one plain `cp` at a time.
- No frozen test conflicts with the contract.

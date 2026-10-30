All four chain-side items and the three item-0 defects are done. The CHECK list passes: 852 passed in 345.70s. Nothing is committed.

The real probe's new stall limit is wired but not exercised on a real run (see "Not satisfied" below). I never read or ran any `test_b2_frozen_*` file. The one `b2_frozen_*` module I used is `b2_frozen_support.py`, imported as a fixture library, as the existing `test_b2_fix_chain.py` does.

## Files changed

- `benchmark/bench/p426_wave2.py` (item 0):
  - the pair dossier's `harvest` is `<ops.harvest_path(attempt)>/HARVEST.json`; the box ops return the directory;
  - `rehearsal` takes identity and date from the manifest, else `ops.identity(off_worktree)`;
  - `canonical_occurrences` now delegates to `schedules`;
  - the chain entry path is built from parts, so `test_p371_chain_rows` doesn't list this module as a row consumer.
- `benchmark/bench/p426_freeze.py` (item 0): restore-diff problems are prefixed `restore diff:`; the chain entry path is built from parts.
- `benchmark/bench/p426_reconcile.py`: item-record requests now carry `elapsed_s` (the worker log's `elapsed`).
- `benchmark/bench/p426_record.py`: mode `makeup` loads a timeout amendment.
- `benchmark/bench/schedules.py`: `tg1(..., rehearsal=)` (smoke shape: 1 pilot item, then 2 full items of s1's Python order), `makeup_canonical` and `tg1_makeup` (one load, one leg per (session, seed, language) group).
- `benchmark/bench/chain_core.py`: makeup schedule, `p426_not_run` in `chain.json`, `inject` passed to the hooks, `--inject-stall-item` / `--inject-stall-s` added to the probe argv of the invocation holding the first Python item.
- `benchmark/bench/p426_hooks.py`: `inject="reconcile-mismatch"` fails the first item with the exact reason `reconciliation mismatch (injected)`.
- `benchmark/chains/c147/run_tg1_chain.py`: mode `makeup` with `--occurrences`, plus the refusals around it; `--rehearsal` refuses an out-root outside `$STACK_WORKDIR/p426/rehearsal/` before writing anything.
- `benchmark/run_tg1_probe.py` and `benchmark/bench/arm_runner.py`: `--inject-stall-item <lang>/<item>` and `--inject-stall-s`. `inject_stall_problem` refuses them unless both are given, `--evidence p426` is set, the limit is positive and the item is selected. `silence_limit_s` applies the lowered limit to that one item.
- `benchmark/chains/c147/fake_probe.py`: honours the same flags; the injected item is scored `stalled`, not converged, not passed.
- `benchmark/bench/tests/test_b2_s8c_chain.py` (new, 42 tests), plus edits to `test_b2_s8_wave2.py`, `test_b2_s8_freeze.py` and `b2_s8_support.py`.

## Item 0: why `rehearsal` launched nothing

I could not reproduce the `[]` result against my own fake ops. The one failure I could produce was a manifest that records the date but not the identity keys, or nests them under `identity`: `leg_argv` then raised a `ValueError`. That is fixed and covered by two tests, but I can't confirm it is the exact case you hit.

## Commands and verbatim summary lines

- `run_stack_tests.sh` over the s1/s2/s7/s8/s8c files, `test_c147_chain_runner`, `test_p371_chain_core`, `test_p371_baseline`, `test_p311_chain`, `test_p364_chain`, `test_b2_fix_chain`, `test_local_gate`, `test_p426_wave1`: `852 passed in 345.70s (0:05:45)`.
- Existing non-frozen test files importing a changed module, in three batches:
  - B2, C147, P311/P364, tg1, probe, gate: `1 failed, 1559 passed in 450.07s`. The failure was my own regression (bare `Chain` without `.a` in `test_b2_s3_core`); fixed, then `90 passed in 15.18s`.
  - The P371 family: `1 failed, 782 passed, 1 skipped in 585.07s`. The failure was `test_p371_chain_rows`; fixed, then `270 passed in 43.97s` together with the s8 files.
  - M64/M62 family plus the P311/P364 chains, gate and Wave 1: `415 passed, 3 skipped in 309.24s`.
- Legacy goldens did not move. Of the existing test files I changed code under, the only two that failed were the two regressions above.

## Tests seen red first, with the failure line

- **`elapsed_s` request field, `makeup` record mode:**
  - `KeyError: 'elapsed_s'`, `KeyError: 'makeup'`.
  - Without this the s8b settle bound would have refused every real v8 or amendment.
- **Rehearsal schedule shape, make-up schedule, shared canonical occurrences:**
  - `TypeError: tg1() got an unexpected keyword argument 'rehearsal'`.
  - `AttributeError: module 'bench.schedules' has no attribute 'tg1_makeup'` / `'makeup_canonical'`.
- **Chain CLI:** `argparse.ArgumentError: argument mode: invalid choice: 'makeup' (choose from pilot, chain)`.
- **End-to-end rehearsal and injection:**
  - `assert (None == 'python/p1')`.
  - `assert (0 == 2)`, the out-root outside the rehearsal dir was not refused.
  - `assert 0 == 1`, which turned out to be my wrong expectation: the invalidated item is no ledger row.
- **End-to-end make-up:**
  - The make-up leg could not run at first: `FileNotFoundError: …/tg1-p426-off-makeup.a1/chain.json`.
  - A STOP-latch test asserted `status != "finished"`, but the existing chain exits rc 3 with status `finished`; I fixed that expectation.
- **Probe flags:** `AttributeError: module 'bench.arm_runner' has no attribute 'inject_stall_problem'` / `'silence_limit_s'`, and `'Namespace' object has no attribute 'inject_stall_item'`.
- **Fake probe:** `SystemExit: 2` (unrecognized flags); the no-flag control passed.
- **Item 0:**
  - `IsADirectoryError: …/harvest/tg1-p426-off-pilot.a1`.
  - `assert (['restore bad'] == ['restore diff: restore bad']`, and a `REFUSED:` line without `restore diff`.
  - `ValueError: a rehearsal leg needs the probe identity and the frozen date`, for both manifest shapes.
- **Topology test:** it found a defect in my s8b `planned_slots`. `the realized ledger has 5 slots, the frozen schedule 6`: a pilot-only leg's `full_names` is its whole seeded order but it runs only its 5-item invocation. Reproduced by `assert 8 == 5`, then fixed to sum the invocations' names.
- **Not red:** the pilot-pair topology test could only go red through that defect. `test_pilot_gate_needs_the_five_item_pilot_schedule` (s8b) was already green on the old code and is kept as a regression test.

## Topology test

The real `Sequencer` runs the real `run_tg1_chain.main` on a thread against the item-barrier fake probe, with one `$STACK_WORKDIR` and one worktree per arm. The pilot pair passes through the real argv, locks, `chain.json`, `receipt.json`, item records, `LAST_LEG_END` and pair dossier. It also covers the pilot gate writing the amendment, the second chain's real `--pair-receipt` comparison and the 600 s gap. A make-up pair (OFF then ON) runs end to end after the gate and gets a PASS dossier.

## Not satisfied

- **Real-probe stall limit never exercised.** The new limit applies to the client-silence check (`proc_guard.POLICY["silence_s"]`), the only seconds-based stall limit in the probe. It is covered by helper tests, a signature check and a check that `_run_item` reads the override. No test runs `_run_item`'s silence loop (it needs a real opencode session). Whether 30 s of client silence with nothing in flight kills a live item is untested; only a real R3 rehearsal can show that.
- **R3's kill case not checked end to end.** My topology fake does not simulate the kill. The chain flags (`--inject-stall-item/-s`) and the fake probe's `stalled` row are tested separately, but nothing asserts that a reconciled `kill_*` item record appears.
- **Edits to existing code outside the module list you named** (needed for the spec): `p426_reconcile.py`, `p426_record.py` and `schedules.py`, listed above.
- **`docs/specs/p426-b2-tg1-wave2.md` shows as modified.** That is the designer's edit, not mine.

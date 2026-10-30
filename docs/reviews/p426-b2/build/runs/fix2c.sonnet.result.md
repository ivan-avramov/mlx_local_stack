The `p426_dnf` record's `invocation` is now the integer index of the aborted invocation in `chain.json` `progress.invocations`. The fix2b suites exit with code 0 and no failures. Nothing is committed or pushed, and I did not run the frozen tests.

**Test first.** I added `test_the_p426_dnf_record_names_its_invocation_by_index_and_load_gen_as_int` to `test_b2_fix2.py`. It drives a real DNF leg and failed with `assert (<class 'str'> is int)` — the record carried `pilot/….L0.pilot.a1.jsonl`. It checks that:
- `invocation` and `load_gen` are ints;
- `progress.invocations[dnf["invocation"]]["load_gen"] == dnf["load_gen"]`;
- the slot is in that invocation's `expected_slots`;
- the sidecar record agrees.

**Fix.** In `chain_core.py` (`handle_p426_incomplete`), `invocation` is now the record's position in `progress["invocations"]`, found by identity. `load_gen` was already an int.

**Rows path.** I kept it under a new key, `invocation_file`. I found no reader of `p426_dnf.invocation`: harvest and the sequencer use only `slot` and `item_record`. The ledger entries keep their own `invocation` as the rows path, which `chain_rows`, the harvest and the watcher read; I left those alone since you only named the `p426_dnf` record.

**Fixture change.** The first run failed with `StopIteration` in the s3 bare-chain tests, because their `scenario` never put `rec` into `progress["invocations"]`. A real chain always registers it first (`register_invocation`), so I changed the shared `incomplete` helper in `test_b2_s3_core.py` to register it rather than loosening the code.

**Files changed:**
- `benchmark/bench/chain_core.py`
- `benchmark/bench/tests/test_b2_fix2.py`
- `benchmark/bench/tests/test_b2_s3_core.py`

**Run.** The wrapper ran `test_b2_fix2.py`, every `test_b2_s*.py`, `test_b2_fix_chain.py`, `test_c147_chain_runner.py` and `test_p426_harvest.py` with `-q --tb=short -p no:cacheprovider`. The final run ended `[exited with code 0]` with no `FAILED` lines. The run just before it failed on the `StopIteration` above, which the fixture change fixed.

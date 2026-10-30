The `p426_dnf` record is now self-hashed and the sidecar is exclusive-created. The fix2c suites exit with code 0 and no failures. I did not run the frozen tests, and nothing is committed or pushed.

**Test first.** I added `test_the_p426_dnf_record_and_its_sidecar_are_self_hashed_and_the_sidecar_is_exclusive` to `test_b2_fix2.py`. It drives a real DNF leg and failed with `assert (False)` from `p426_hooks.sealed_ok` on the `chain.json` record. It checks that:
- the `chain.json` entry has a correct self-hash;
- the sidecar equals that entry, is named `<slot_file>.json`, and refuses a second write with `FileExistsError`.

A second test, `test_the_p426_dnf_self_hash_is_over_the_portable_form`, checks that no machine path leaks into the record. It already passed and stays as a guard.

**Fix.** Both changes are in `handle_p426_incomplete` in `chain_core.py`:
- The record is sealed with `ph.seal` after the portable-path conversion. The hash covers the portable form that `chain.json` stores.
- The sidecar is written with `ph.write_exclusive` instead of an atomic replace, so it holds the same sealed record and is never overwritten.

**Other immutable records.** Checked by reading the code that writes each:

| Record | Self-hash? | How |
|---|---|---|
| Ready, item, DNF item | yes | `p426_hooks.write_exclusive` |
| Receipt | yes | sealed by `p426_receipt.arm_receipt`, written by `write_exclusive` |
| Pair dossier | yes | `write_exclusive` |
| Leg record | yes | `write_exclusive` (`p426_wave2` line 571) |
| Rehearsal manifest, v8 base, timeout amendment | yes | `p426_freeze` writes them through `write_exclusive` |
| `HARVEST.json` | yes | sets `doc["sha256"]` from the same canonical form |

My new test also verified, at runtime, the receipt and every ready/item/`.dnf.json` record of a real DNF leg. I did not execute the freeze, leg-record or `HARVEST.json` writers here. Their paths are covered by the existing `test_b2_s8_freeze`, `test_b2_s8_wave2` and `test_b2_s9_harvest` runs, which passed. I found none lacking a self-hash.

**Files changed:**
- `benchmark/bench/chain_core.py`
- `benchmark/bench/tests/test_b2_fix2.py`

**Run.** The wrapper ran `test_b2_fix2.py`, every `test_b2_s*.py`, `test_b2_fix_chain.py`, `test_c147_chain_runner.py` and `test_p426_harvest.py` with `-q --tb=short -p no:cacheprovider`. It ended `[exited with code 0]` with no `FAILED` lines.

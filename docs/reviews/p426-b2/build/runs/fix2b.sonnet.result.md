`p426_dnf.arm` now carries the predictor arm (`off` or `on`) instead of the scaffold label. The five requested suites exit with code 0 and no failures, and nothing is committed or pushed.

**Test first.** I added `test_the_p426_dnf_record_carries_the_predictor_arm_not_the_scaffold_label` to `test_b2_fix2.py`. It is parametrized over `off`/`off` and `mtp`/`on` and checks both the chain record and the sidecar. It failed with `At index 5 diff: 'A' != 'on'`. The label in that test is `A`, not `oc`, because the bare-chain fixture's scaffold label is `A`; the cause is the same.

**Fix.** In `chain_core.py`, the record written in `handle_p426_incomplete` now sets `arm=self.p426_arm_name()` instead of `view["arm"]`.

**Readers.** No code reads `p426_dnf.arm`.
- The sequencer's make-up `arm_of_dnf` comes from the operator's occurrences file, which already uses `off`/`on`, and `schedules.py` only merges it.
- The harvest only checks DNF slots, item records and sidecars, never the arm.
- `p426_wave2.py` and `p426_freeze.py` only count DNF records.

**Test fixture change.** Making the fix broke three older tests because the bare chain in `test_b2_s3_core.py` has no `a` attribute. I gave it `c.a = SimpleNamespace(predictor="off")` and changed its old `d["arm"] == "A"` assertion to `"off"`.

**Files changed:**
- `benchmark/bench/chain_core.py`
- `benchmark/bench/tests/test_b2_fix2.py`
- `benchmark/bench/tests/test_b2_s3_core.py`

**Command and result.** I ran the wrapper with `-q --tb=short -p no:cacheprovider` over `test_b2_fix2.py`, `test_b2_s1_cli.py` through `test_b2_s9_harvest.py` (all `test_b2_s*.py`), `test_b2_fix_chain.py`, `test_c147_chain_runner.py` and `test_p426_harvest.py`. It ended with `[exited with code 0]`. The output was dots only, with no F or E, and the last progress line was `[100%]`.

I did not run the frozen tests.

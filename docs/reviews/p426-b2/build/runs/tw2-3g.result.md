# Delivery 3g: topology world now has an operator email; your four verification tests can't pass on the baseline

**Result:** on the s9 copy, the three topology cases pass. The s7 DNF-record test fails on both copies. On the baseline, all four fail, as they must: the baseline (`61d31bcd`) has no candidate code. I have no script for the final-fix-round copy, so this pin was not verified against the code that has it. Nothing was committed or pushed.

## Tests touched (post-reveal 3g)

- **`b2_frozen_fix_support.py`, `Topology.operator_emails`:**
  - It now returns `["op.erator@corp-mail.example"]`, a fake held in a class constant `OPERATOR`. The tag is post-reveal 3g, citing §16.8 "after delivery 3f".
  - It is the same address add_scrub and add_sequencer use.
  - No topology case asserts on addresses; its fake harvest and publish ignore `emails`. So nothing else needed changing.
- **Last §16.8 bullet (`p426_dnf.arm` is `off` / `on`):** my tests already agree, so I changed nothing.
  - `test_b2_frozen_s7_locks.py:206` expects `dnf["arm"] == "off"` on an OFF pilot.
  - `b2_frozen_add_support.py:317` writes DNF records with `arm=arm` (`off` / `on`).
  - No test expects `oc`.

## Runs

**Baseline, `../bin/run_stack_tests.sh`:**

- Support checks: `55 passed in 17.21s`
- The three topology cases plus the s7 DNF-record test: `4 failed, 72 deselected, 3 warnings in 0.29s`
  - Topology ×3: `KeyError: 'rc'`. The sequencer thread died before `main` returned anything; the import of `bench.p426_wave2` sits outside the `try`, and the baseline has no such module.
  - s7 `test_new_the_p426_dnf_record_carries_the_section_16_1_fields`: `assert 2 == 0`.

**s9 copy, after `sync_to_s9.sh`, with `run_candidate_s9_tests.sh`:**

`1 failed, 3 passed, 72 deselected in 17.78s`
- **Passed:**
  - `test_fix_p536_topology_the_real_sequencer_runs_the_pilot_pair_through_the_real_chain`
  - `test_fix_p536_topology_one_makeup_leg_runs_through_the_real_chain`
  - `test_fix_p536_topology_a_makeup_leg_that_stops_early_records_its_unrun_occurrences`
- **Failed:** s7 `test_new_the_p426_dnf_record_carries_the_section_16_1_fields` (`assert 2 == 0`).
  - Same test, same failure as the 3f run, which logged `CHAIN ABORT: DNF refused: the rows of the failed attempt do not validate … row_arm: python/p1 None != 'oc'` for the sibling DNF tests.
  - The `row_arm … 'oc'` in that message is the chain's row check, separate from the DNF record's `arm`.
  - This is the flat-layout DNF item already queued for the final fix round, class (a).
- **Caveat:** the s9 copy predates the empty-email pin, so the topology passes there show only that the new fixture is consistent. They do not exercise the pin.

To confirm the fixture against the pin itself, run those three topology cases and the s7 DNF-record test on the final-fix-round copy.

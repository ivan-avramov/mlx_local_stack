Round-1 disposition:

- P1 — resolved. The output-dependent exclusion was removed. One-sided family tokens remain in the panel, and `test_v2.py:54-62` covers both one-arm and two-arm cases.
- P2 — resolved by reversion. `kv_validate_prompts` again receives the complete `inputs` at `benchmark/bench/p426_panel.py:1875`; no pre-validation filtering remains.

Round-2 finding:

P3 — major — `benchmark/bench/p426_panel.py:1225,1387`

`KV_LEAK_PATTERNS` blocks `n16` but not the other arm labels `X` or `V`. Scenario: an answer says “this is the X arm.” `_kv_leaks` finds nothing, so the packet is emitted and directly identifies its arm. `test_v2.py:65` tests only an N16 arm reference, missing X/V. This is pre-existing, not introduced by fix2.

The family-token change itself does not reveal the arm: both arms use the same registry model, and one-sided topical mentions remain answer content rather than arm metadata.

The MTP-lever path is unchanged: `_a7_leaks` still rejects family tokens at `benchmark/bench/p426_panel.py:774-775`. The change is limited to `_kv_write_packets`, covering all KV members—including KV A7 packets—not only A2.

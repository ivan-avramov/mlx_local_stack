P1 — minor — `benchmark/bench/p426_verify.py:528-529,551-552,581-590`

The MTP path also adopts latest-attempt selection through `_sequence_pair`, but discards `superseded`. Scenario: `off-s1.a1/on-s1.a1` is followed by a valid `off-s1.a2/on-s1.a1` pair. `verify_a7` now selects the latter but emits no audit trail for the former, contrary to the stated reporting rule. KV correctly emits it at lines 2105 and 2138.

Otherwise, no safety finding:

- Later INVALID attempt: no dossier is created; latest matching count is zero, so verification refuses.
- One-arm rerun: if sequencing continues, the unchanged partner is reprocessed and the mixed pair is gated/recorded; if interrupted first, verification refuses.
- Make-up attempts use separate leg/session names and cannot match A7 member validation.
- Latest attempt without a corresponding pair record refuses.
- A recorded FAIL pair is selected but remains `accepted: false` through dossier verification.

Caveat: pilot pair recording precedes the timeout-amendment gate, so “accepted” here means the pair dossier passed—not that the full pilot/amendment gate succeeded.

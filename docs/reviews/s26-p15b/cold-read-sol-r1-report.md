Round 1 of 3 findings:

P1 — blocker — `benchmark/bench/p426_verify.py:540-545`  
Superseded `leg.json` validation fails open. Missing, unreadable, non-object, or tampered/unsealed records all become “not clean.” Scenario: change a clean a1’s `speed_valid` to false without updating its self-hash—or delete/corrupt the file—then provide a valid a2 rerun reason. B8 accepts the replacement.

P2 — blocker — `benchmark/bench/p426_verify.py:535`  
Only attempts named by superseded pair records are checked. Scenario: `sequence.json` retains clean x-a1 and chosen x-a2 in `legs`, but the old pair record or its `x` field is removed. `superseded` is empty/incomplete, so neither cleanliness nor a2’s rerun reason is checked; the clean result can be replaced.

P3 — major — `benchmark/bench/p426_verify.py:548-550`  
Multi-hop reruns validate only the final chosen attempt’s reason. Scenario: speed-invalid a1 → unlabelled a2 → labelled a3, with pair records for all three. Both superseded records look up a3’s reason, so the missing a2 reason is concealed.

P4 — major — `benchmark/bench/p426_verify.py:541`  
`old_name` is used as a path without member-name or confinement validation. A superseded record naming `../outside.a1` can read outside `wave2` and add a `wave2/../…` B8 input. Signals rejects that input path; the KV panel path may still freeze the B8 SHA, producing inconsistent consumer behavior. Valid in-tree superseded inputs are otherwise handled correctly: signals rehashes them and FROZEN binds the changed B8 SHA.

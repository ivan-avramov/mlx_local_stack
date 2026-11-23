P1 — Location: `candidate-3.diff`, `benchmark/bench/p426_verify.py`, `a8_frozen_record_reasons`, early `got == want` return; severity: major; evidence: confirmed.

Problem: Every decider attempt naming the v8 base is accepted immediately, bypassing all amendment checks. The sequencer assigns v8 only to pilot legs and amendment to every decider leg, while the specification requires “pilot on the v8 base, a decider leg on the amendment” and rejection of anything else.

Concrete failure scenario: An otherwise-valid s1/s2 pair records `v8_base.sha256` in both chains—because of stale records or a misrouted `record_path`. The candidate accepts it even when `amendment.json` is absent, unsealed, bound to another pilot dossier, or otherwise invalid. Such a pair can feed the verdict without running on the campaign’s post-pilot frozen identity. The frozen tests explicitly omit this case, and the implementation tests preserve it for legacy fixtures.

Proposed change: For `session == "pilot"`, accept only the v8 hash. For s1/s2/reload, accept only the amendment hash after `a8_amendment_problems(...)` returns no problems. Update fixture worlds to publish a valid amendment and add a negative test where a decider names the v8 hash.

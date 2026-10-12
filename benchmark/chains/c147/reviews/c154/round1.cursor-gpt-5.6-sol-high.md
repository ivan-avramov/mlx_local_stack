R1 — should-fix — `benchmark/bench/token_turn_gate.py:392-402,530`  
`uncharged_trailing()` accepts missing/invalid content or timestamps as zero/`None`; malformed text can raise `TypeError`. Fail closed unless content is a list, relevant text is string, timestamps are non-bool integers, and `streamed >= created`. Otherwise the promised uncharged evidence is not auditable.

R2 — should-fix — `benchmark/bench/tests/test_token_turn_gate.py:521-550`; guard at `benchmark/bench/token_turn_gate.py:517`  
The negative matrix omits missing trailing assistant and missing/non-`error` finish, leaving new guards mutation-untested. Add those cases plus a prior `budget_hit` interaction asserting `client_inactivity` remains primary and both flags persist. Existing focused suite passes: 110 tests.

R3 — nit — `benchmark/bench/token_turn_gate.py:30-34`; `docs/specs/m62-token-turn-gate.md:142`  
Binary strings confirm `dEd()` fixes the 60-minute default and only durable events refresh it. However, the wording overstates the export as universally usage-free: interruption during a tool after provider completion can retain finish/usage, and the run handler can suppress its inactivity error after an earlier error. The current predicate correctly aborts these variants under the exact-shape ruling; scope the documentation to the observed mid-stream shape.

Downstream accounting, strict scoring, precedence, chain validation, and probe-SHA identity handling are otherwise correct.

cleared after fixes (R1, R2)No further action needed; the completed reviews were already incorporated.

P1 — A8 screen/decider dependence is modelled incorrectly  
- Location: `benchmark/bench/m76_sim.py:1147-1154,1232-1254`; `docs/specs/m65-tg2-corpus.md:94-100,115-116`; `docs/specs/m76-b4-tg2-legs.md:23-25`
- Severity: major
- Evidence: confirmed.
- Problem: The candidate assumes separate, independent screen and decider items. The actual design uses nested prefixes: screen items are the first half of the decider. The direct simulation and tests reproduce the same incorrect independence, so their agreement is circular.
- Concrete failure scenario: A negative first-half result triggers the decider and remains represented in its final data, making `P(decider clean | trigger)` differ from the unconditional decider rate used in `1−t+tq`. Thus 77.83% A8-path cleanliness and 39.42% joint clean-PASS can be biased.
- Proposed change: Simulate one nested A8 dataset per replication, applying the screen to its prescribed prefix and the decider to the complete dataset with the actual reuse/session semantics. Add a test where prefix outcomes predict the final verdict.

P2 — The joint result omits a required A5 ship gate  
- Location: `benchmark/bench/m76_sim.py:1176-1185,1323-1327`; `docs/specs/m76-b7-1-joint-plan.md:35-36`; `docs/specs/m76-tq4-certification.md:243-246,294-297`
- Severity: major
- Evidence: confirmed.
- Problem: The specification permits assuming only A5’s absolute per-arm ≥0.85 gates. The candidate additionally assumes the per-task point-estimate gates are met, although ship requires each task’s estimate ≥−5 pp.
- Concrete failure scenario: Retrieval can be below −5 pp while compensating chain-4 gains let the pooled exact test PASS. The candidate counts that run as clean. This can also change whether A5-2L “pays.”
- Proposed change: Include both per-task point gates in the A5 clean term and recompute committed/A5-2L joint probabilities. Keep only the absolute accuracy gates as assumptions. Do not make gate failure trigger follow-up unless separately pre-registered.

P3 — A8’s large-harm HOLD is absent from “clean PASS”  
- Location: `benchmark/bench/m76_sim.py:1147-1161,1323-1328`; `docs/specs/m76-tq4-certification.md:286-288`; `docs/specs/m65-tg2-corpus.md:107-110`
- Severity: major
- Evidence: confirmed.
- Problem: The ship rule retains the decider’s per-language large-harm HOLD, but the candidate treats decider PASS plus no interaction flag as clean and does not model per-language decider outcomes.
- Concrete failure scenario: The macro decider passes while one language crosses its pre-registered HOLD threshold; the report counts a clean path although shipment is blocked.
- Proposed change: Resolve the authoritative HOLD threshold, simulate per-language decider results, and include HOLD in A8 cleanliness. Until then, label joint probabilities as conditional on no large-harm HOLD. Add a macro-PASS/one-language-HOLD test.

P4 — Headline GPU hours exclude mandatory stage-3 work  
- Location: `benchmark/bench/m76_sim.py:993-1000,1196-1210`; `benchmark/results/m76/b7-simulation/REPORT.md:302-304`; `docs/specs/m76-tq4-certification.md:300-318`
- Severity: minor
- Evidence: confirmed.
- Problem: The 48.9/65.8-hour figures exclude the tg1 pilot/reload and stage-3 smokes while being labelled expected/worst GPU hours for the plan. The caveat appears only below the table.
- Concrete failure scenario: Reserving the reported worst budget omits unavoidable work; §9’s corresponding whole-stage estimate is approximately 71 hours before smoke recalibration.
- Proposed change: Include mandatory GPU work, or relabel the column “modelled comparison-leg GPU hours” and show whole-stage totals alongside it.

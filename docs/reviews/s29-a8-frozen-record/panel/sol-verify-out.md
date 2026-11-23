P1 — RESOLVED

- Location: `candidate-4.diff`, `benchmark/bench/p426_verify.py`, `a8_frozen_record_reasons`
- Severity: major (original)
- Evidence: confirmed — decider sessions naming the v8 SHA now unconditionally receive a rule-3.6 reason before amendment acceptance; tests cover valid, absent, and tampered amendments.
- Problem: The previous amendment-check bypass is removed.
- Concrete failure scenario: A decider chain naming the v8 base is now rejected and cannot feed the verdict.
- Proposed change: None.

P2

- Location: `candidate-4.diff`, `benchmark/bench/p426_verify.py`, `a8_amendment_problems`
- Severity: major
- Evidence: confirmed — validation checks only the seal, kind, corpus, v8 binding, and pilot-dossier binding. It never validates required amendment fields such as language walls, `leg_deadline_s`, `settle_bound_s`, or `created`.
- Problem: A sealed but structurally invalid amendment passes rule 3.6, contrary to R1’s requirement that the amendment be “sealed and valid.” The fixture report explicitly confirms these fields are unchecked.
- Concrete failure scenario: Reseal an amendment after deleting `leg_deadline_s`, retain the correct identity bindings, and have decider chains name its new SHA. `a8_amendment_problems` returns no reasons, allowing those pairs to feed the verdict despite not naming a valid campaign amendment.
- Proposed change: Validate the complete canonical amendment schema and field constraints—preferably through the amendment writer’s shared validator—and add negative tests for resealed amendments with missing or invalid deadline/wall fields.

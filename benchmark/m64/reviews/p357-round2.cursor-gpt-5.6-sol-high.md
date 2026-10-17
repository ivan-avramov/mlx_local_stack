Q3, Q5, and Q6 are resolved. Direct sampling is unbiased; `run()` tests detect the old generator; all three documents declare the pooled rule invalid, preserve estimation-only, and give the 0/400 upper bound.

Q7 — LOW, non-blocking — `benchmark/m64/power_sim.py:5`  
Failure: module docstring still says pairs come from a feasible joint table, while implementation samples differences directly.  
Fix: update the sentence to describe direct difference sampling.

Q8 — LOW, non-blocking — `docs/specs/m64-scaffold-arms.md:303-305`, `benchmark/m64/POWER_SIM.md:42`  
Failure: the spec requires shared-session-effect simulation, while the report explicitly leaves it owed. This does not affect the estimation-only conclusion.  
Fix: mark that sensitivity as waived/deferred under the operator’s wash direction.

VERDICT: CLEARED

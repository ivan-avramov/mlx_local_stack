Q1. Missing/stale audits → `AuditMissing`, matching resume refusal, provisional counts; absence/SHA/version tests pass.
Q2. Repository denies → root, `.git`, clone, HTTP, `www`, raw mirrors and casing tests pass.
Q3. Narrow patterns → wildcard URLs dropped and recorded; host/owner-root and unknown-source tests pass.
Q4. Pending reruns → per-model counts and provisional-label tests pass.
Q5. Worker identity → PID/model-path recording and mismatch/missing refusal tests pass.
Q6. Operator review → non-runnable jobs and strict-score exclusion tests pass.
Q7. Non-web contacts → flagged, excluded, never returned as rerun jobs; tests pass.
Q8. Auditor wording → cross-language/API transfer, partial descriptions and near-complete definitions; prompt tests pass.

Q9. Validation: **282 targeted tests passed**, then **70 recovery tests passed**, including all 40 new regressions. Verified nice level 19; no full suites.

Q10. Hermetic binary checks: repository strings appeared in loopback URL paths, exercising real opencode resource matching. Both webfetch and `git clone` were denied; **zero target requests**.

Q11. Open questions: none. Older rows lacking worker identity refuse reruns. Changes remain uncommitted.
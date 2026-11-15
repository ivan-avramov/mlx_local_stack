P1
- Location: `m76_ids.py:476-487`
- Severity: minor
- Evidence: confirmed
- Problem: The new validation precedes source/current-plan validation, changing diagnostic precedence and masking those refusals.
- Concrete failure scenario: A record is both out of band and tied to a stale report; `load()` reports only the band violation.
- Proposed change: Run the band check after the existing source and plan checks.

P2
- Location: `test_s23_p88_ids_band.py:20-43`
- Severity: minor
- Evidence: confirmed
- Problem: Tests mutate only the first regular and first smoke item and never load the real committed record.
- Concrete failure scenario: A regression checking only each list’s first element passes, while later out-of-band entries escape; committed one-look shape compatibility also remains untested.
- Proposed change: Test middle/last regular and smoke entries, both bounds, and load the committed `ids.json` with its current plan.

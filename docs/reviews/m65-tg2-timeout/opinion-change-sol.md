P1
- Location: `test_tg2_grade_timeout_impl_docker.py:25-31`; `test_tg2_grade_timeout_fe_docker.py:39`
- Severity: major
- Evidence: confirmed
- Problem: Both suites violate erratum v1a’s 5/5/15/18-second minimums.
- Scenario: Normal box load times out Java/C++ compilation instead of execution, making the real-image gate flaky.
- Proposed change: Use Rust 5 s, JavaScript 5 s, C++ 15 s, Java 18 s in both suites.

P2
- Location: `tg2_grade.py:579-598`
- Severity: minor
- Evidence: confirmed
- Problem: D2 omits `.tg2-out-collect-*`, contrary to the literal requirement for every marked step.
- Scenario: Collect timeout classifies correctly, but partial tar evidence is lost and `collect.out_sha256` is null.
- Proposed change: Explicitly amend the spec to exempt collect. TEEing collect output would require revisiting the 64 MiB report-volume budget.

P3
- Location: `tg2_grade.py:36`; `m65/tg2_universe.json:5,11`; `m65/tg2_universe.py:252-268`; `m65/tg2_draw.json:315`
- Scope request
- Evidence: confirmed
- Problem: The grader is v3 while the frozen universe remains v2 and the draw pins that universe.
- Scenario: The universe loader refuses the committed universe, blocking Stage 3b.
- Proposed change: Before Stage 3b, re-freeze the universe, regenerate its sidecar and draw, and update downstream universe pins.

P4
- Location: `test_tg2_grade_timeout_impl_fake.py:99-140`; `test_tg2_grade_timeout_fe_fake.py:212-285,359-368`
- Severity: minor
- Evidence: confirmed
- Problem: Neither test set combines file-only marker evidence with OOM/mem-kill, tests no-marker mem-kill, or makes read-back itself OOM/mem-killed. Source ordering is currently correct, but these branches are unpinned.
- Scenario: A future marker/resource-order regression could classify a started OOM as infrastructure or a never-started mem-kill as model while both suites pass.
- Proposed change: Add fake cases for file-only OOM/mem-kill, no-marker mem-kill, and read-back OOM/mem-kill.

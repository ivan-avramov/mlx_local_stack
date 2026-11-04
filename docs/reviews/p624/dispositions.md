# P624 (gate: a baseline skip that ran and passed) — findings and dispositions (designer), 2026-11-04

Sources: test-writer delivery 2 (Claude Sonnet 5.5, F1–F3, verdict merge), panel opinion (GPT-5.6 Sol High P1–P2; GLM 5.2 F1–F7),
implementer ambiguity notes P1–P4. All original.

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| Sol P1 / GLM F1 / TW F1 / impl P3 sets drop duplicate-count differences | major | adopted (fix 1) | spec: every other skip difference fails exactly as today; compare multisets: a skipped id beyond its baseline count → today's `+` problem; a duplicated baseline line → problem `skip baseline lists an entry more than once` |
| Sol P2 one clean duplicate testcase masks a failing one | major | adopted (fix 2) | an id is "ran and passed" only if every testcase with that id is free of skipped / failure / error |
| GLM F2 missing junit after rc 0 folds into the new message | minor | adopted (fix 3) | a distinct problem `pytest junit not written`; the skip checks do not run |
| GLM F3 `baseline_skips_ran` `[]` with no baseline | minor | declined | `problems` names the missing baseline; the key stays always present |
| GLM F4–F7, TW F2–F3 test gaps (both problems at once; `-[...]` tail; multi-child testcase; parametrised id; FAIL-receipt key) | test gap | to the test-writer (delivery 3) | |

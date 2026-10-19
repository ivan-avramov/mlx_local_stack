# tg2 universe freeze report

Grader `m65-tg2-v2`, image `sha256:98559f41e4c63683d1154253ebe09050264d35e42a8bbb3b15b2e52bea21bf44`, polyglot `7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f`; universe sha256 `ff76573bf70fbe6d2ad9cf7d4f0e60e35e6ead9ffbbde9b335d94da19f8d7480`.

Per item: 3 fresh reference runs (identical collected leaf sets, all pass) and 2 fresh stub runs (identical collected leaves, `baseline_failing > 0`).

| Language | candidates | N_actual | excluded |
|---|---|---|---|
| cpp | 26 | 26 | 0 |
| java | 47 | 45 | 2 |
| javascript | 49 | 48 | 1 |
| rust | 30 | 30 | 0 |

## Exclusions (every one with its reason)

- `java/ledger`: baseline_failing == 0 (the untouched stub already passes every leaf)
- `java/tree-building`: baseline_failing == 0 (the untouched stub already passes every leaf)
- `javascript/ledger`: baseline_failing == 0 (the untouched stub already passes every leaf)

## Determinism

- reference runs with identical leaf sets: 149 of 149 valid items
- stub runs with identical leaf sets: 149 of 149 valid items
- cpp reference grade seconds: median 5.0, max 8.4; per-item timeout = max(180, 3 x max)
- java reference grade seconds: median 9.2, max 13.8; per-item timeout = max(180, 3 x max)
- javascript reference grade seconds: median 2.4, max 4.1; per-item timeout = max(180, 3 x max)
- rust reference grade seconds: median 1.7, max 11.4; per-item timeout = max(180, 3 x max)

## Optional leaves (JS `test.skip`, excluded from scoring by id)

- `javascript/palindrome-products`: ['palindrome-products.spec.js::Palindromes largest palindrome from four digit factors']
- `javascript/robot-name`: ['robot-name.spec.js::Robot all the names can be generated']

## Skip-form rewrites

- 1566 skip forms rewritten across valid items (JS xtest/xit/xdescribe, Java @Disabled)

## Deprecated / inverted scan

- no item declares itself deprecated or inverted

# tg2 universe freeze report

Grader `m65-tg2-v1`, image `sha256:98559f41e4c63683d1154253ebe09050264d35e42a8bbb3b15b2e52bea21bf44`, polyglot `7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f`; universe sha256 `e8abba5c7c6f7f0e789c849acbcc6b036b09f4e95dffdacfa0ba501a18a5c9fa`.

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
- cpp reference grade seconds: median 4.9, max 8.2; per-item timeout = max(180, 3 x max)
- java reference grade seconds: median 9.0, max 13.8; per-item timeout = max(180, 3 x max)
- javascript reference grade seconds: median 2.2, max 3.8; per-item timeout = max(180, 3 x max)
- rust reference grade seconds: median 1.6, max 9.7; per-item timeout = max(180, 3 x max)

## Optional leaves (JS `test.skip`, excluded from scoring by id)

- `javascript/palindrome-products`: ['palindrome-products.spec.js::Palindromes largest palindrome from four digit factors']
- `javascript/robot-name`: ['robot-name.spec.js::Robot all the names can be generated']

## Skip-form rewrites

- 1566 skip forms rewritten across valid items (JS xtest/xit/xdescribe, Java @Disabled)

## Deprecated / inverted scan

- no item declares itself deprecated or inverted

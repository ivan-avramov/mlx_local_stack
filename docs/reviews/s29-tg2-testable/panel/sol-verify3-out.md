P1 — Round-2 P8: NOT FULLY RESOLVED  
- Location: `configgen/emitters/opencode.py::_case_forms`, `_tg2_shell_lookups`; generated carrier permissions
- Severity: major
- Evidence: confirmed
- Problem: Common shorthand forms are denied, but arbitrary mixed case is not. `_case_forms` only covers lower-, upper-, and selected brand-case spellings.
- Concrete failure scenario: `npx degit ExErCiSm/rust /tmp/r` or `npm install github:ExErCiSm/rust` is allowed, violating T4’s “any letter case” requirement.
- Proposed change: Perform lookup matching on a case-normalized resource, with alternating-case tests across shell and webfetch forms.

P2 — Round-2 P9: RESOLVED  
- Location: `benchmark/bench/p426_reconcile.py::_k1_bound`
- Evidence: confirmed
- Why: Matching UIDs bind UID-bearing lines. UID-less real logs require the item session on the preceding completion and consecutive lifecycle evidence with `in_flight` 0→1→0. Partial UID, foreign-session, interleaved, and malformed shapes remain INTEGRITY. The recorded window exercises the serial path.

P3 — Round-2 P10: NOT FULLY RESOLVED  
- Location: `configgen/emitters/opencode.py::_tg2_shell_lookups`, `TG2_PS_FETCHERS`, `TG2_HOST_PREFIXES`
- Severity: minor
- Evidence: confirmed
- Problem: The original examples are allowed, but fetch-command and host patterns still deny some harmless local paths.
- Concrete failure scenario: `curl -o problem-specifications.json https://doc.rust-lang.org/std/` matches `*curl *?roblem-?pecifications*`; `cat exercism.org.txt` matches a host-position rule. Neither performs solution lookup.
- Proposed change: Match lookup terms only in parsed remote operands of network/repository commands, not anywhere later in the command text. Add these cases as allowed tests.

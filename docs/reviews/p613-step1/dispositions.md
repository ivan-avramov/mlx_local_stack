# P613 step 1 (B8 + B6 for A7) — findings and dispositions (designer), 2026-11-03

Sources: test-writer delivery 2 (Claude Sonnet 5.5, F1–F9, verdict fix-then-merge), panel opinion (GPT-5.6 Sol High via
cursor-agent, findings S1–S12, verdict not ready), side agent (P616). All original unless marked.

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| S1 item records not required 1:1 with rows | blocker | adopted (fix 1) | a missing record drops an item from one arm's speed / acceptance: selection bias |
| S2 / F1 one bad key rejects the session | major / minor | adapted (fix 2) | reject the key alone; reject the pair when the schedules differ |
| S3 make-up only "pending" | major | adapted (fix 3) | no make-up exists; a make-up record refuses (fail closed); substitution = residual for when one exists |
| S4 noise floor from rejected diagnostic pairs | major | adopted (fix 4) | |
| S5 DNF slots dropped from noise flips | major | adopted (fix 5) | |
| S6 speed source unchecked | major | adopted (fix 6) | |
| S7 / F7 identity hash unbound | major / minor | adopted (fix 7, fix 15) | wrong identity would suppress panel judging (step 3) |
| S8 / F4 pooled cross-epoch headline | minor | adopted (fix 8) | spec says per arm |
| S9 / F2 −5 pp float edge | minor | adopted (fix 9) | |
| S10 / F3 B8 sha of re-dump | minor | adopted (fix 10) | |
| S11 / F8 coverage from sequence only | minor | adopted (fix 11) | |
| S12 / F9 non-atomic writes, traceback on missing dir | minor | adopted (fix 12) | |
| F5 nonconv kind flag | minor | adopted (fix 13) | spec §4.11 wording |
| F6 `*.dnf.*` globs | minor | adopted (fix 14) | |
| P616 flag crosswalk | — (scope request, designer) | adopted (fix 16) | flags from arm-asymmetric cuts / noise read as evidence otherwise |
| test-writer §4 #1–#8, #10 | test defects | to the test-writer (amend, refreeze) | lookups / fixtures; candidate values present |
| test-writer §4 #9 | spec ambiguity | resolved by fix 2 | key-only rejection now the rule |

Post-Accept (designer, behaviour-preserving; allow-shorthand): the naming hook read two local variables named `low` as model shorthand; renamed to
`below` (p426_signals.py, acceptance flag items) and `lowered` (test_p613_signals_output.py) — the one edit to a frozen test, a
rename only; 241 / 241 still pass.

Post-Accept 2 (P617): the gate on `7a3cf6b0` failed the P371 R7 invariant (direct chain-row parsing outside `bench.chain_rows`).
Fixed: rows parsed by `chain_rows.read_rows`; behaviour on the committed data unchanged (sheet byte-identical); 257 tests pass.

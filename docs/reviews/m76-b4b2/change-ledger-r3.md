# M76 B4b-2 — change review round 3 of 3 (LAST; panel verify of fix round 2, candidate 3): ledger

GLM 5.2 High: D1–D4 resolved, D5's decline holds, NOTHING OF SUBSTANCE. Claude Sonnet 5.5: D1–D4 resolved, D5 holds. GPT-5.6 Sol High:
two majors. Review budget exhausted → the open findings go to the operator (S28-P22).

| id | finding (raised by) | designer judgement | why |
|---|---|---|---|
| E1 | D1 counts ledger entries only after filtering `kind == "row"`; a second entry of another kind for the same slot is ignored (Sol F1) | real, synthetic-only | the runner writes one ledger entry per slot; exactness: exactly one entry per (slot, rerun index), its kind matching the scored source, before any filtering. |
| E2 | D5's "unreachable" is false: the chain writes the ledger entry at the barrier answer, before `.continue` (`chain_core.py:3231`); a probe that then fails to observe the answer aborts with stage `done` (outcome present); the abort route sees the slot already ledgered and records the accounting fault only in `p426_accounting_faults` + the sealed sidecar (`chain_core.py:2910`), leaving the slot attempt and ledger unmarked; B8-A8 then REFUSES the whole record (Sol F2) | real, rare, material | traced. A real runner record would block the A8 record. Fix on the CONSUMER side (the runner is in the tg2 identity closure; editing it would rotate the identity under the running decider): the chain's accounting record (list entry + sealed sidecar) is the recorded fact; a slot-attempt / ledger / row marker, where present, must agree; a marker without the list + sidecar, or a list entry without its sidecar, refuses. Red test on the runner's own branch shape. |

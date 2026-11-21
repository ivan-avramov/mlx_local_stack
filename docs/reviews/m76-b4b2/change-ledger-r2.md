# M76 B4b-2 — change review round 2 of 3 (panel verify of fix round 1, candidate 2): ledger

Panel: GPT-5.6 Sol High, GLM 5.2 High (NOTHING OF SUBSTANCE), Claude Sonnet 5.5 (fresh). B1–B16 resolved per GLM / Sonnet traces
except as below.

| id | finding (raised by) | disposition | why |
|---|---|---|---|
| D1 | `_a8_accounting`: ledger agreement uses `any(...)` (a contradictory duplicate entry passes); `p426_accounting_faults` collapsed to a set (duplicates, non-objects, wrong `sidecar` ignored) (Sol P1) | adopted | exactness where record binding is the protection: exactly one ledger entry per (slot, rerun index) whose marker is the slot's; every chain-list entry an object, unique, naming the expected sidecar. |
| D2 | ISO-zoned timestamps not checked non-negative / finite (Sol P2) | adopted | same rule as numeric `t`. |
| D3 | The model is bound only to the attempt's own schedule (`picks[0]`), a self-comparison (Sonnet P1) | adopted | bind it to the registry pick (`ENTRY`): `schedule.picks[0] == ENTRY` and every manifest / row model equal to it. |
| D4 | `int(rerun_index or 0)` raises on a malformed value (an uncaught traceback, not a refusal) (Sonnet P2) | adopted | `type(x) is int`, else `RefusalError`. |
| D5 | An accounting fault on a slot whose ledger entry already exists would refuse (Sonnet P3, hypothesis) | declined | unreachable: the runner writes the ledger entry after the barrier answer (`chain_core` done path), so no slot has a ledger entry when its accounting fault is recorded; the test-writer's fixtures follow the runner. |
| D6 | B11 / B12 unverified (Sol P3); frozen conflicts (Sol P4, Sonnet P4) | covered | test-writer delivery 3 (B12, fixture amendments); B11 = the designer's real-record acceptance on the new-identity pilot before the panel freeze; the `f2b61127…` goldens run in the stack gate (the commit exists on `main`). |

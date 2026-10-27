# B2 final fix round queue (designer's judged list; the four-eyes fix round after the strict verify)

- Flat-layout DNF refusal: `validate_partial` applies the per-arm `arm_row_problems` to flat tg1 rows (fix-pass report; frozen add_ledger + 7 s7 DNF tests, fix cases R3 / P23 stay red until fixed).
- P39 `after_attempt` reads `/metrics` before writing the item record (unreadable metrics → no record).
- P40 entry refusals must also print the §16 stderr `REFUSED:` line.
- P41 `p426_settle_bound` must not swallow a `RecordError`.
- P42 seam signatures: `interpreter_inventory(pid)` overloaded with a path; `worktree_state()` vs §16.4 `worktree_state(path)`.
- P43 `write_dossier` verdict consistency (a passing dossier with pair problems).
- P44 kill detection: a non-empty `termination.killed` on a normally completed item (check the real probe's semantics).
- P45 note: `generic_pred_s` rename changed every tg1 config hash (record it; legacy differential passes).
- (s7 scope, not fix round) P36 ready-barrier checks (registry sha, lifecycle hash, clean worktree); P37 entry checks before the router.
- (tests) P38: the test-writer adds coverage for snapshot drift after load and "a legacy chain runs none of the receipt checks".

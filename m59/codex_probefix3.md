- **P1 / N1:** Corrected all five README points; stale text → verified current behavior.
- **P2 / N2:** Added completed/context-overflow `aborted` tests: 2 green before and after.
- **P3 / N3:** Accept `aborted` only on the final assistant message of gate kills: 3 red → green.
- **P4 / N4:** Record signature plus scrubbed error: 6 red → green.
- **P5 / N6:** Refuse mismatched A4 router config hashes: 1 red → green; compatibility cases pass.

Focused: **154 passed**.  
Full: **3420 passed, 2 skipped, 2 warnings**.  
`STACK_WORKDIR` unset for suites; elevated rerun resolved sandbox denial of `ps`.  
Diff check clean. Only three allowed files changed. **No commit.**
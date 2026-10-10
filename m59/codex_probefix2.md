**P12:** Implemented within the allowed files, uncommitted. Pre-existing `ts.md` untouched.

| ID | Change and red → green evidence |
|---|---|
| **P13 / F1** | Gate-killed `aborted` exports become graded rows; other provider errors abort. **Real binary:** old classifier `ABORT` → `ROW`, `nonconv_kind=stalled`. Six fake-binary kill cases pass. |
| **P14 / F2** | Gate writer→probe reader test failed → passes; mismatched receipts refuse. Keys read: `pass`, `model`, `opencode_version`, `exe_sha256`, `run_id`, `router.pid`, `router_pid`, `carrier_sha256`. |
| **P15 / F3** | Only explicit `--limit ≤ 5` bypasses A4. Missing-receipt refusal tests now pass, including a 22-item leg. |
| **P16 / F4** | Rows/manifests record `fixed-by-carrier` and the mock-capture test name. Capture proves **102400 with body cap; 512 without**, both at `limit.output=512`. Metadata assertions failed → pass. |
| **P17 / F5** | Destination failures stamp `transport_abort.signature=destination_check`, without drift. Timeout/malformed/mismatch continuation tests failed → pass. |
| **P18 / F6** | Comparison pinned to `b533fff`; altered-body mutant rejected, missing-base skip verified. Exact bytes preserved except requested semicolon splitting in two metric functions. |
| **P19 / F7** | Discovery requires plugin proof. **Real binary:** removing `OPENCODE_PRINT_LOGS` previously succeeded → now `REFUSED`, zero model requests. |
| **P20 / F8** | Retried-then-stalled regression added. Removing the existing consecutive-start check fails the test; restored check aborts correctly. |
| **P21 / F9** | Instruction sources inventoried from scratch ancestors and bench HOME. Planted-source assertion failed → passes. |
| **P22 / F10** | Continuations append only the six specified fields. Recursive-history assertion failed → passes. |

**P23:** Style cleanup completed; legacy function ASTs unchanged. `PATH`, `TERM`, and `NO_COLOR` now affect the policy hash; regression tests pass. All **10 v2 real-binary cases ran**.

**P24:** Final verification:

```text
3408 passed, 2 skipped, 2 warnings in 304.53s (0:05:04)
75 passed in 1.28s
configgen check: exit 0
git diff --check: clean
```
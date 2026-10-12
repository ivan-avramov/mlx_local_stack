R4 — should-fix — `benchmark/bench/token_turn_gate.py:408-410`  
Huge integer timestamps pass validation but division raises `OverflowError`, escaping `reconcile()` instead of failing closed. Catch conversion overflow and raise `TransportAbort`; add a `10**400` timestamp test. Focused and adjacent suites otherwise pass (364 tests).

cleared after fixes (R4)Adjacent tg1 contract suite passed: 245/245. No additional findings; R4 remains the only required fix.

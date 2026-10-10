- **P15 — Item 1:** Every `URLError` aborts. Raw first-probe timeout DNF remains. **Red:** wrapped timeouts at 90/100 seconds incorrectly continued.
- **P16 — Item 2:** Request-local timing and first-call qualification exclude recovery failures. **Red:** recovery timeouts failed to abort; `wall_s` was 117 instead of 100.
- **P17 — Item 3:** Isolated manifest failures, recorded `stamp_errors`, protected original exception chaining, and added archival warnings. **Red:** stamp failures masked the cause; best-effort `KeyboardInterrupt` returned normally.
- **P18 — Item 4:** Pinned C106-before-archive ordering. Brief correction: the empty-queue path lacked that check; fixed.
- **P19 — Item 5:** Added slow non-outcome coverage, preload-duration assertions, and home/login/workdir scrubbing and truncation checks.
- **P20 — Item 6:** README now documents the precise classification, stamp lifecycle/scope, and CLI behavior.

**P21 — Verified by running:**

```text
65 passed in 0.90s
3260 passed, 7 skipped, 2 warnings in 266.12s (0:04:26)
```

The full-suite result used an isolated `$STACK_WORKDIR` outside the sandbox. With the inherited workdir, results were **1 failed, 3266 passed**: an unchanged real-DSH integration test violated the per-test workdir guard. The initial sandbox attempt crashed importing MLX. These limitations remain separate from C119.

**P22:** Real-socket urllib behavior was not independently remeasured. Scope, whitespace, and literal-PII checks passed. Changes remain uncommitted; no git state-changing commands ran.
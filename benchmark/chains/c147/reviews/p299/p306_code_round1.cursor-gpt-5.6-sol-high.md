Review of commit `91873722` against parent `21066227`. Read-only; tests were not executed.

1. P1 — should-fix — descendant branches lack direct regression coverage  
   File: `benchmark/bench/tests/test_c157_proc_guard.py:498-526`

   Failure scenario: the tests cover only an empty descendant set and a live known descendant. A regression that never prunes non-empty sets—or incorrectly prunes reused/unreadable descendant identities—would not be caught.

   Fix: add tests for:
   - root and recorded child both gone → prune;
   - child PID reused or identity unreadable → retain/scan replacement;
   - `(pid, None)` root or child: absent → prune, occupied → retain.

Assessment:

- For records actually pruned, `_fully_gone()` is cleanup-equivalent. Known-identity PID reuse means the recorded identity is gone; the replacement remains subject to the next tick or cleanup’s full scan.
- `created=None` identities are conservative: they count as gone only when the PID is absent. This may retain records cleanup could resolve, but cannot false-clear.
- Descendants are added before pruning on every tick where the root remains listed. Children appearing after the root vanishes are an existing attribution limitation that retaining the frozen record would not solve.
- No new false-clear found.
- Cost is bounded by the existing caps: at most 32 roots and 2,048 total identity probes per tick, under the lock. Potentially expensive, but finite.
- Expected race exceptions are contained: `NoSuchProcess`, `StopIteration`, `AccessDenied`, and `TransportAbort`. Unexpected exceptions still terminate the monitor and are surfaced fail-closed, as intended.

Verdict: cleared after fixes P1

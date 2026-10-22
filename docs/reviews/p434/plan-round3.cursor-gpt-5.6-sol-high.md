G4 — OPEN — Without a shared reservation, a benchmark can still start during a long gate step; rechecking before the next step detects the collision only after measurements were disturbed.

G5 — OPEN — `git fetch` without pruning or explicit refspecs can leave stale remote-tracking refs, so `--remotes=<remote>` may exclude commits no longer reachable remotely and miss reintroduced leaks.

G6 — OPEN — `GATE_MIN_COMMIT` is only an ancestry floor; switching to any older descendant containing an obsolete gate can reactivate that policy and its receipts.

H1 — CLOSED — v3 sets the required absolute `PYTHONPATH` and adds unmocked shim tests from all three repository roots.

No new J findings.

VERDICT: DISAGREE G4,G5,G6

P2 — Round-4 items

- P27 — **Yes.** D1/D2 are consistently marked RULED.
- P28 — **Partly.** Digest, rendered settings, credential environment, and MCP identity are bound, but masked-hash canonicalization and `WOLFRAM_APP_ID` are unspecified.
- P29 — **Partly.** Restarts cover arm switches and recovery, but not every block/arm leg, session, pick, or reload boundary; adjacent same-arm legs can inherit suspension state.
- P30 — **Yes.** Pre-item probing, failure classification, recovery, and `transport_dnf` are defined.
- P31 — **Yes.** Third-party egress is disclosed and `web_searches` evidence is registered for P201.
- P32 — **Partly.** Offline/live determinism is corrected, but “result count” has no numeric value.
- P33 — **Yes.** The dsh no-MCP exception is consistent throughout.

P3 — Problems in v5 §5.5

1. MCP runs per item, but schema verification occurs at chain entry, block start, and exit—when no MCP process necessarily exists.
2. Restarting only “at every arm switch” does not ensure a fresh service for every scheduled arm leg.
3. The canary query, pass criteria, and MCP-hang deadline are unspecified.
4. Settings hashing lacks a canonical serialization/redaction algorithm; “the wolframalpha key” should be `WOLFRAM_APP_ID`.
5. The runner-owned Compose project/container identity and collision behavior are undefined despite the daily stack using the same service and port.
6. Running-image verification does not identify which `docker inspect` fields establish the registry digest.
7. The required raw response and per-engine evidence may not be exposed by the eventual MCP package; package adoption must prove that capture path.

P4 — BUILD go

**No, narrowly.** The implementation gaps are expected BUILD work: the existing carrier remains compaction-off without MCP, `tg1_runner.py` is opencode-only, `proc_guard.py` lacks G1/watchdog behavior, and `web_audit.py` only accepts existing opencode evidence. The specification’s remaining problem is that §5.5 still permits materially different lifecycle and failure-detection implementations.

P5 — Minimum edits to agree

1. Restart before every block × arm leg and at session, pick, reload, and recovery boundaries.
2. Define an isolated Compose project/container identity and refuse foreign ownership of port 8080.
3. Pin numeric result count—10 matches existing qualification—plus the canary query, parameters, success rule, and MCP timeout.
4. Define schema verification through an ephemeral checker or each per-attempt MCP instance.
5. Specify canonical masked-settings hashing, exact credential variables, digest-verification fields, and require the selected MCP path to preserve the mandated evidence.

AGREE WITH CHANGES: arm-leg lifecycle boundaries; executable MCP verification; pinned result count/canary/timeouts; canonical identity checks; isolated container ownership

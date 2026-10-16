Reviewed commit `649f2e2e`; later HEAD changes only add the round-7 prompt.

P1 — Round-6 minimum edits

1. **Partly.** Port/mount constraints are stated, but `lsof` cannot uniquely identify a container’s port proxy on macOS’s shared Docker/OrbStack backend; `.HostConfig.PortBindings` proves configuration, not realized publication.
2. **Yes.** Complete raw JSON is retained while exactly the first ten SearXNG-ordered results reach every client.
3. **Partly.** `tools_sha256` provides durable request evidence, but its canonicalization and relationship to the raw MCP `tools/list` hash are undefined, and only the first receipt is reconciled.

P2 — Problems introduced by v7

- The runtime-port proof is not directly executable as written. It should verify realized `.NetworkSettings.Ports`/`docker port` output and use `lsof` only to exclude foreign listeners.
- Two different artifacts are conflated: the MCP server’s raw `tools/list` schema and each client’s translated provider-request `tools` array. They need distinct named hashes and canonicalization rules.
- Recording `tools_sha256` on every receipt but validating only the first permits later task requests to change tool exposure. Auxiliary or compaction requests may legitimately omit tools, so allowed hashes must be defined by request class rather than ignored.

P3 — Code verification

The existing carrier remains compaction-off without MCP; Compose uses `:latest` with the generated read-only mount; `tg1_runner.py`, `ProcessGuard`, `judge_gate.py`, and `web_audit.py` remain opencode/M38-oriented and lack the specified M64 behavior. Those are correctly listed as BUILD work, not additional specification defects.

P4 — BUILD go

No, narrowly. The statistical, scheduling, audit, watchdog, and treatment contracts are complete, but the new runtime and tool-schema proofs still permit incompatible implementations.

P5 — Minimum edits

1. Define realized loopback-port verification and exact mount source/type/destination/read-only checks without requiring a unique host proxy PID.
2. Define canonical serialization and separate `mcp_tools_list_sha256` from `request_tools_sha256`.
3. Reconcile every receipt against pre-registered request-class tool hashes; missing or unexpected hashes abort the attempt.

AGREE WITH CHANGES: executable runtime port proof; distinct canonical MCP/request tool hashes; per-request tool-hash reconciliation

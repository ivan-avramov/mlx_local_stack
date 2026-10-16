P1 — Round-7 minimum edits

1. **No.** The spec still relies on `HostConfig.PortBindings` plus `lsof`; realized publication and exact mount source/type are not verified.
2. **No.** It still uses one ambiguous `tools_sha256`, without separately canonicalized MCP-list and provider-request hashes.
3. **No.** It still reconciles only the first request, not every receipt against request-class expectations.

P2 — Problems introduced by v8

No substantive v8 exists at `d2278f95`. The specification blob is identical to v7 (`649f2e2e`); the commit adds only the round-7 review while claiming the three fixes. The spec still labels itself v7 and says only rounds 1–6 were addressed. This is a provenance/review-state defect.

Code verification confirms the carrier remains compaction-off without MCP, Compose remains `:latest`, and the runner, guard, judge, and auditor remain pre-M64 implementations. Those are expected BUILD work, not additional specification defects.

P3 — BUILD go

No. The intended v8 edits are absent, and the unresolved port/mount and tool-schema contracts still permit incompatible implementations.

P4 — Minimum edits to agree

1. Add realized loopback publication verification and exact mount type/source/destination/read-only checks; use `lsof` only to reject foreign listeners.
2. Define canonical JSON precisely and separate `mcp_tools_list_sha256` from `request_tools_sha256`.
3. Reconcile every receipt against pre-registered task/compaction/auxiliary tool hashes; missing or unclassified receipts abort.
4. Commit those changes and update the spec’s v8/round-7 status.

DISAGREE: the requested v8 specification is absent at d2278f95 and all three round-7 minimum edits remain unapplied

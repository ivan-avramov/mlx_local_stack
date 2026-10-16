Reviewed commit `655b7370`; current HEAD only adds the round-6 prompt.

P1 — Round-5 minimum edits

1. **Yes.** Restart now occurs before every block×arm leg and all named lifecycle/recovery boundaries.
2. **Yes.** The Compose project, container, label, and foreign-port refusal are specified.
3. **Yes.** Result count, canary query/parameters/success criteria, and 30-second MCP timeout are stated.
4. **Yes.** Lifecycle checks use an ephemeral MCP checker; attempts inspect the effective first-request tool list.
5. **Yes.** Canonical masking, credential names, digest fields, and raw-response adoption requirements are defined.

P2 — Round-5 P3 problems

1. **Yes.** Ephemeral `tools/list` checks remove dependence on a persistent MCP process.
2. **Yes.** Every block×arm leg receives a fresh SearXNG container.
3. **Yes.** Canary and MCP-hang contracts are explicit.
4. **Yes.** Canonical JSON hashing and `WOLFRAM_APP_ID` are specified.
5. **Yes.** Ownership and collision behavior are defined.
6. **Yes.** `.Image` plus the resolved image’s `RepoDigests` establish the digest.
7. **Yes.** Adoption must preserve raw JSON, with a minimal in-repo MCP fallback.

P3 — Problems introduced by v6 §5.5

1. **Runtime binding proof is incomplete.** Identity checks omit exact port binding and mount inspection. A correctly labelled/image-matched container with `0.0.0.0:8080` or the wrong settings mount could pass. Require exact loopback publication, sole-listener correlation, and a read-only `/etc/searxng/settings.yml` mount matching the hashed file.
2. **“Result count 10” lacks execution semantics.** SearXNG does not expose that as the pinned request parameter used here; the qualification’s ten-result behavior was downstream truncation. Specify that the MCP server retains the complete raw JSON as evidence but returns exactly the first ten results to every client.
3. **Per-attempt MCP verification has no evidence path.** §5.5 says the first model request’s tool list proves the attempt’s MCP instance, but §7 receipts do not contain tool schemas and production wire capture is not otherwise required. Add a canonical `tools_sha256` to the first-request receipt or capture the client’s actual MCP `tools/list` exchange.

The existing carrier’s compaction-off/no-MCP configuration, Compose `:latest`, opencode-only audit path, current ProcessGuard behavior, and M38 judge implementation are expected BUILD work already covered by acceptance requirements—not additional specification blockers.

P4 — BUILD go

No, narrowly. The design is otherwise complete, but these three gaps allow materially different search exposure, result payloads, and provenance checks.

Minimum edits to agree:

1. Pin and verify exact port bindings and settings mounts, including sole ownership of loopback port 8080.
2. Define ten-result truncation versus preserved raw evidence.
3. Define durable per-attempt MCP tool-schema evidence and reconciliation.

AGREE WITH CHANGES: runtime port/mount proof; result-count truncation semantics; per-attempt MCP-schema evidence

P1 — Round-7 minimum edits

1. **Yes.** Realized loopback publication and exact mount type/source/destination/read-only state are now checked; `lsof` only excludes foreign listeners.
2. **Yes.** MCP `tools/list` and provider-request tools now have distinct names and precise canonical-JSON hashing.
3. **Partly.** Every receipt is reconciled, but request-class assignment is undefined and could circularly depend on the tools hash being validated.

The requested diff is substantive; `96ca67c3` genuinely changes the v7 specification.

P2 — Problems introduced by v8

The new request-class mechanism lacks an independent classification rule. One implementation could classify from client events or wire semantics; another could classify by whichever registered hash matches. The latter could mislabel a later task request that loses tools as an auxiliary request and accept it, defeating the intended every-request protection and changing treatment exposure.

P3 — BUILD go

No, narrowly. Port/mount and hash-domain issues are resolved, but request classification still permits materially different enforcement.

P4 — Minimum edit to AGREE

1. Require each receipt to be joined one-to-one to an independently classified client/wire request; classification must not use `request_tools_sha256`. Unmatched, ambiguous, or conflicting classifications abort. Add positives for a legitimate tool-less compaction/auxiliary request and a later task request incorrectly dropping/changing tools.

Nits: call the failure an “unclassified request,” not an “unclassified hash”; consider representing absent `tools` separately rather than storing `"absent"` in a field named `*_sha256`.

AGREE WITH CHANGES: define independent request classification and receipt-to-request reconciliation

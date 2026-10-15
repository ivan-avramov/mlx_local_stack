No actionable findings. Read-only review; no tests run.

1. **P4 — P1 closed.** `answer_key.py:119–123` requires a valid digest or exact frozen-record membership. The omitted/null tests would fail against round-1’s unrestricted fallback. Independently calculated hashes match all five inventory entries.

2. **P5 — P2 closed.** `web_audit.py:187–190` selects exact-context first, legacy second, before applying retry policy. The regression test checks both orders, exactly one call, and the resulting label; round-1’s legacy-success skip would fail it.

3. **P6 — P3 closed.** The genuine legacy-context test now strips the digest, inventories the records, changes context, and checks acceptance, counts, and unchanged sidecar length. This compatibility test could pass against round-1’s intended legacy behavior; that is appropriate. P1’s negative tests distinguish unrestricted acceptance. Both precedence orders are covered.

4. **P7 — Inventory edge cases are fail-closed within the stated scope.** Copying an unchanged grandfathered record into another sidecar retains its original evidence identity; it cannot match a different row/session/path/hash. An identical identity remains the same grandfathered evidence, including the explicitly allowed context-change exception. Editing the record changes its hash; re-hashing alone cannot extend the inventory. The JSON `note` is ignored. A missing inventory returns an empty allowlist, rejecting all digest-less records. All five frozen records are resolved `generic` records, so the stricter validation strands no existing unresolved operator-resolution workflow.

5. **P8 — Acceptance assessment.** Context changes independently invalidate new audits and trigger re-auditing; grandfathered audits remain accepted and counted; scoring remains independent of installed auditor CLIs. No new path accepting different evidence or prompts was found. Test success and byte-identical report regeneration remain author-reported, not independently executed here. The exact numbered C163 acceptance criteria were not included in the supplied round-1 text.

cleared

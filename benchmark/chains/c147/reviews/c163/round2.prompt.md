Cold review round 2 (read-only; do not run tests — no writable temp dir in your sandbox; author's results below). Same change as round 1 (C163) with fixes for your three findings. Repository: current working directory, uncommitted working tree; review `git diff` plus the new files benchmark/bench/tests/test_c163_audit_context_identity.py and benchmark/bench/legacy_audit_records.json.

Author's response to round 1:
- P1 (missing digest = unrestricted legacy escape hatch): fixed with a FROZEN INVENTORY. `answer_key.legacy_audit_records.json` lists the canonical sha256 (`record_digest`, sort_keys JSON) of the 5 digest-less records in the 3 committed sidecars (built by `build_legacy_inventory`); `_valid_audit` now requires a 64-hex `context_sha256`, except a record whose digest is None/omitted AND whose record_digest is in the inventory. A test asserts the inventory equals the committed digest-less records exactly (5). Tests: omitted and explicit-null digests on new records → missing; grandfathered → accepted, counted, not re-audited, also after a context change.
- P2 (legacy success blocks retry of the digest error): fixed — `audit_rows` now picks the record the scorer would apply (exact digest key first, legacy key second) and re-audits it only if it is an audit_error and --retry-errors; the `done` set is run-local dedupe only. Test: legacy docs + digest audit_error for the same evidence, both sidecar orders, exactly one call, label becomes the retried one.
- P3 (misnamed test; precedence only legacy-last): renamed to digest-mismatch; added the genuine legacy-after-context-change test (accepted, counted, zero auditor calls); digest-vs-legacy precedence parametrized over both orders.
- Fixture helper `test_m61_p202.decision` now writes `context_sha256` like a real record (38 legacy-shaped fixture records were otherwise rejected — expected under P1); one exact-dict assertion gained `legacy_audits=0`.
Author's results: 9 audit-related test files, all passing (see below); reports P223/M63 regenerate byte-identical (generators print no legacy count); full suite running.

Your round-1 text:
1. **P1 — medium — `benchmark/bench/answer_key.py:332` (validation at `:92`): missing digest is an unrestricted legacy escape hatch.**  
   The normal writer always emits the digest, but any newly appended otherwise-valid record with the field omitted **or explicitly null** receives legacy treatment. After a context edit, that record can supply a passing label and suppress re-auditing. Nothing establishes that it predates C163.

   **Fix:** grandfather a frozen inventory of existing legacy records and require a valid digest for everything else. CLI versions are not audit-schema versions, and the unchanged prompt SHA provides no migration boundary. A schema version helps detect malformed new records, but alone cannot prevent omission from masquerading as legacy. Test omitted/null digests on new records separately from genuine grandfathered records. This is a migration-validation gap, not a claim of protection against arbitrary sidecar forgery.

2. **P2 — medium — `benchmark/web_audit.py:185`: legacy success blocks retry of the authoritative digest error.**  
   With an accepted legacy `docs` record and a matching digest-bearing `audit_error`, scoring selects the error. Under `--retry-errors`, the digest key is excluded from `done`, but the legacy success remains; the fallback membership check skips the evidence. The row stays unresolved despite an explicit retry request.

   **Fix:** select the applicable record using the scorer’s exact-first, legacy-second precedence, then apply the retry policy to that record. Test both sidecar orders and verify exactly one auditor call. A latest **legacy-only** `audit_error` is correctly excluded from `done`; that case itself is not broken.

3. **P3 — minor — `benchmark/bench/tests/test_c163_audit_context_identity.py:108`: the named legacy-context test never creates a legacy record.** <!-- allow-shorthand: review wording, not model names -->
   It retains the generated digest and repeats the changed-status case. Consequently, it does not establish the documented behavior that a grandfathered legacy record remains accepted, counted, and not re-audited after a context change.

   **Fix:** rename this test to describe digest mismatch, then add a genuine legacy-context-change test covering acceptance, disclosure, and zero auditor calls. Parameterize digest-versus-legacy precedence over both sidecar orders; the current test covers only legacy-last.

not cleared

Task: verify P1–P3 are genuinely closed (would each test still pass against the round-1 code or a fail-open implementation?), check the inventory mechanism for new holes (e.g. a grandfathered record copied into ANOTHER sidecar or row; a record edited then re-hashed; the `note` key in the JSON; `legacy_record_digests` on a missing file returning empty — is that fail-closed?), re-check acceptance criteria (1)–(3) from round 1, and anything new introduced by the fixes. Output: numbered findings with severity, file:line, failing scenario, fix; one-line verdict "cleared" or "not cleared".

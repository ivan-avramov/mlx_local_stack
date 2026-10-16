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

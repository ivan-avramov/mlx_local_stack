Review of commit f76eaa4b:

1. P1 — medium — `benchmark/bench/answer_key.py:119-137`, `benchmark/web_audit.py:184-188`  
   A grandfathered legacy `audit_error` cannot be operator-resolved. Appending `operator_label` changes its canonical digest, so `_context_digest_ok()` rejects the resolution as absent from the frozen inventory. `--retry-errors` then re-audits it, violating P309. Current committed legacy records are all `generic`, so this is latent.  
   Fix: validate a legacy resolution against the inventory digest after removing operator fields, while retaining the exact-predecessor check in `accepted_audits()`.

2. P2 — medium — `benchmark/README.md:258-271`, `benchmark/web_audit.py:263`  
   Documentation and CLI help still say `--retry-errors` retries latest errors, without excluding operator-resolved errors. They also omit the new nonzero `AuditorVersionError` behavior and no-append guarantee.  
   Fix: document “unresolved errors only,” deferred version probing, and failure semantics; update help text.

3. P3 — low — `benchmark/chains/m61/drive_ab.sh:22`  
   This frozen driver logs a failed audit but continues and ultimately reports the A/B return code. With P309, an unreadable version can leave smoke audits absent while the driver reports success. Live C147 has no such caller, and `run_m61_rr.py` correctly fails closed.  
   Fix: abort on audit failure if replay remains supported; otherwise explicitly mark this frozen driver incompatible with current audit semantics.

4. P4 — low — `benchmark/bench/tests/test_p309_audit_retry_and_version.py:31-73`  
   Missing regression coverage allowed P1 through and leaves ordering behavior unpinned. Add tests for:
   - grandfathered legacy error plus valid operator resolution;
   - resolution superseded by a later genuine retry, across same and different versions;
   - resolved error with an unavailable version probe;
   - preserving an existing sidecar when version probing fails.

Verdict: cleared after fixes P1–P4

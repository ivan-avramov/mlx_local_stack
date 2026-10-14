A1. blocker — `benchmark/bench/answer_key.py:243,266-274` — Any matching JSON record is authoritative without validating `reason` or audit provenance; a fabricated `docs` record without `reason`, or an `audit_error` plus operator resolution with no preceding audit, enters `strict_n`. Validate the full audit schema and require resolutions to reference a preceding exact-key audit record. Deliberate-tampering resistance additionally requires authenticated receipts, not self-asserted strings.

A2. should-fix — `benchmark/web_audit_cursor.py:49-53` — Unlike `web_audit.py`, non-positive `--timeout` values are accepted and produce append-only `audit_error` records requiring `--retry-errors`. Reject `timeout <= 0` in argument parsing and test it.

Verification: requested suite passed 96/96; the new tests bite the parent because `declared_auditors()` is absent there. Prompt/evidence/version binding, auditor precedence, no-web behavior, exception handling, read-only empty workspace, and tg1 identity inclusion otherwise check out.

not clearedFollow-up finding:

A3. should-fix — `benchmark/bench/answer_key.py:237-243` — Existing P201 “offline” tests stub only Codex, so reports invoke the real `cursor-agent --version`. Inject/stub all declared version probes and add a no-web/no-subprocess test.

The prior `not cleared` verdict is unchanged.

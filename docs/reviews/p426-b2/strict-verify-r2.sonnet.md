**Round-1 findings: only the two I raised could be checked (4 and 12). I did not verify 1–3 or 5–11.**

- **4 (sonnet's part: an ON item with only ≤1-token requests): resolved.** `p426_reconcile.py:137-140` flags such an ON item as `unengaged` when it is judged as a whole item. `p426_freeze.py:159` does the same for a whole leg. I did not check the DNF half of finding 4 or its tests.
- **12 (secrets parsing, JSON `Bearer`, non-UTF-8): resolved.**
  - `parse_assignments` now parses with `shlex.split(..., comments=True)`. A trailing comment and a quote followed by a comment are both handled. A credential-keyed line that doesn't parse raises `SecretsError` naming the key only (`p426_secrets.py:55-78`).
  - The `bearer` pattern accepts `"Authorization": "Bearer …"` and the `=` form (`p426_secrets.py:135`).
  - `Gate.check` (`p426_harvest.py:406-417`) decodes with surrogateescape, records the source as lossy and scrubs and scans the decoded text. It encodes back with the same error handler and refuses with `pii_marker` if a PII marker survives in the scrubbed bytes. So findings F1, F2 and F4 from round 1 are closed.
- **3 (`KV_*`/`TQ_*` allowlist): resolved on the `p426_secrets.py` side.** The exact `STACK_DEFINED_KV_TQ_NAMES` set (lines 19-24 and 46) replaces the prefix rule, so `KV_API_KEY` and `TQ_TOKEN` are credentials. That finding was sol's, but I read the code.
- **1, 2, 5–11:** unverified, because I did not read the code they concern (`p426_dnf`, the sequencer, hooks, the pilot gate and the dossier). Neither a pass nor a fail from me.

**Defect 1 — minor, confirmed in source: `p426_secrets.py:72-77`**
- Problem: `shlex.split` does not expand `$VAR`, `$(cmd)` or backticks. `export FOO_TOKEN=$(cat ~/.foo)` or `$OTHER` becomes the literal text, which is ≥12 characters and "usable". `exact_hits` then looks for that literal, never finds it, and nothing reports that the real value was missed.
- Scenario: a machine-config line that builds a credential through command substitution leaves the exact-value defence off for it. Only the format patterns remain.
- Fix: if a credential-keyed value contains an unquoted `$` or a backtick, raise `SecretsError`, or resolve it from `environ` where possible. Better than silently skipping.

I found nothing else of substance in the files I read. The unreviewed parts (sequencer, locks, hooks, receipt, freeze, dnf, legacy goldens) remain outside this verification.

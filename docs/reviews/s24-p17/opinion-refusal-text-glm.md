## Findings

### F1 — Binary-file branch still echoes matched PII markers into the refusal message
- **Location:** `p426_harvest_publish_excerpt.py:8-9` (the `UnicodeDecodeError` branch).
- **Severity:** major.
- **Evidence:** confirmed in source.
- **Problem:** The fix only patched the text-scrub branch. The binary branch builds `hits = [m.decode() for m in scrub.raw_markers() if m and m in src_bytes]` and then interpolates those literal matched bytes into the message: `f"{rel}: binary file carries PII markers {hits}"`. That is the exact echo the change is meant to eliminate, on a path the same function supports. The request explicitly asks whether matched text can still reach the message by another path in this function — it can, here.
- **Failure scenario:** A binary artifact in the harvest set (compiled blob, sqlite db, gzip, image with embedded path, etc.) contains the bytes for `/home/<name>/`. `_publish` raises `UnicodeDecodeError`, sets `hits = ["/home/<name>/"]`, emits `"...: binary file carries PII markers ['/home/<name>/']"`. That message is returned as a problem, written into `sequence.log`, and the sequencer publishes `sequence.log`. Every later harvest that includes `sequence.log` now sees the marker in the log's own text, refuses, and appends another message echoing the marker — the cascade the fix was designed to close, reopened for any binary input.
- **Proposed change:** Mirror the text branch: report count and pattern name only, never the matched bytes. E.g. `f"{rel}: binary file carries PII: {len(hits)} marker match(es)"`, or name the marker *patterns* (not the matched substrings) if `raw_markers` exposes stable pattern ids. At minimum, drop `{hits}` from the f-string.

### F2 — Test does not cover the binary branch (the path F1 lives on)
- **Location:** `test_s24_p17b_refusal_text.py:11-16`.
- **Severity:** minor.
- **Evidence:** confirmed in source.
- **Problem:** The single test exercises only the text-scrub `else` branch. The `UnicodeDecodeError` branch — the other place in this function that builds a problem message — is untested, so F1 is invisible to the suite.
- **Failure scenario:** F1 ships green; the cascade re-occurs in production on the first binary file with embedded PII.
- **Proposed change:** Add a test that publishes non-UTF-8 bytes containing a marker (e.g. `b"\x00" + MATCH.encode() + b"\xff"`) and asserts `problems` is non-empty and no problem contains `MATCH`.

### F3 — `v.why` is trusted to never contain the matched text, unverified
- **Location:** `p426_harvest_publish_excerpt.py:17`; `test_s24_p17b_refusal_text.py:16`.
- **Severity:** minor.
- **Evidence:** hypothesis (the `piicheck` source is not in the material, so `Violation.why`'s contents cannot be traced).
- **Problem:** The fix's safety rests on `v.why` being a static pattern name rather than a template that embeds the match. The test only checks one pattern (`/home/<name>/`) and only asserts `"/home/" in p` — it does not assert the matched value is absent from `v.why` across the pattern set. If any other registered PII pattern's `why` field interpolates the matched text, the fix reopens for that pattern.
- **Failure scenario:** A pattern whose `why` is e.g. `f"matched {match} in home path"` is added later; the message now echoes the match and the test still passes because it only tests the home pattern.
- **Proposed change:** Add a test iterating over a representative (ideally all) registered PII patterns with crafted inputs, asserting no problem string contains the matched input text; or assert structurally that `Violation.why` is a constant pattern name, not a per-match format.

### On the primary question
The refusal still fires on every match: the comprehension still iterates `piicheck.violations(...)` and emits one problem per violation, so cardinality is preserved. Location is sufficient to find it — `v.path:v.line` plus `v.why` gives file, line, and pattern. The text branch is correctly fixed. The remaining exposure is the binary branch (F1), which is in-scope per the request's "another path in this function" clause and is the substantive defect.

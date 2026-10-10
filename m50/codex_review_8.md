VERDICT: PASS

**P35 — CONFIRMED-FIXED.** [provenance.py:656]($STACK_REPO/benchmark/bench/provenance.py:656) constructs `Request(base_url)`, selects the proxy using `req.type`, and checks bypass using `req.host`. It no longer reconstructs the authority.

The real-`ProxyHandler` differential test covers all 11 specified combinations at [test_provenance_fingerprint.py:1036]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:1036). All three original reproductions now refuse through `assert_served_config` at [test_provenance_fingerprint.py:1056]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:1056).

**P37 — NEW findings:** No new blockers or hardening findings. Previously declined items remain declined.

**P38 — Acceptance and regression assessment**

| Criterion | Result | Evidence |
|---|---|---|
| A1 — Ordering/refusal outputs | PASS | Entry-point refusal tests pass, including before roster requests and output-directory creation: [test_m50_entrypoints.py:190]($STACK_REPO/benchmark/bench/tests/test_m50_entrypoints.py:190), [line 237]($STACK_REPO/benchmark/bench/tests/test_m50_entrypoints.py:237). |
| A2 — Config resolution | PASS | Router cwd/HOME, realpath and file-existence checks remain intact: [provenance.py:755]($STACK_REPO/benchmark/bench/provenance.py:755). Corresponding tests pass. |
| A3 — Destination ownership | PASS | P35 closed; owner, environment, identity and destination checks remain enforced: [provenance.py:800]($STACK_REPO/benchmark/bench/provenance.py:800). No bypass introduced. |
| A4 — Accurate attribution | PASS | Verified block recorded at [provenance.py:1126]($STACK_REPO/benchmark/bench/provenance.py:1126); scrubbing, fingerprint exclusion, resume/history and restart tests pass. |
| A5 — Test adequacy | PASS | Differential test uses a real `ProxyHandler`: [test_provenance_fingerprint.py:1027]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:1027). Discovery tests exercise production lookup code: [line 614]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:614). |
| A6 — Original incident | PASS | Overlay/daily-driver mismatch refuses: [test_provenance_fingerprint.py:488]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:488). Entry guards retain their ordering. |
| A7 — Exceptions/discovery/API | PASS | Restart refusal and attribution-refresh failure remain fatal: [test_m50_entrypoints.py:349]($STACK_REPO/benchmark/bench/tests/test_m50_entrypoints.py:349), [line 413]($STACK_REPO/benchmark/bench/tests/test_m50_entrypoints.py:413). |

**Validation:** 269 focused/regression tests passed. An additional 1,040 no-socket comparisons against real urllib `ProxyHandler` produced zero mismatches. `git diff --check` passed. Opencode config resolution was stubbed during regression testing; no model requests were sent. Repository files were unchanged.
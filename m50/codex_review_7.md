VERDICT: FAIL

**P32 — CONFIRMED-FIXED.** `_split_base` rejects the six reported forms and supplies the scheme used by the guard: [provenance.py:600]($STACK_REPO/benchmark/bench/provenance.py:600), [provenance.py:808]($STACK_REPO/benchmark/bench/provenance.py:808). `router_block` handles parsing failures at [provenance.py:860]($STACK_REPO/benchmark/bench/provenance.py:860). The whitespace/HTTPS regression tests passed.

**P33 — CONFIRMED-FIXED for the reported case.** `no_proxy=localhost:8000` now passes `:8000` and refuses `:8001`: [provenance.py:661]($STACK_REPO/benchmark/bench/provenance.py:661), [test_provenance_fingerprint.py:980]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:980). However, reconstructing the authority introduces the blocker below.

**P35 — NEW BLOCKER: reconstructed authority can falsely bypass proxy detection.**

[provenance.py:613]($STACK_REPO/benchmark/bench/provenance.py:613) normalizes the port; [provenance.py:661]($STACK_REPO/benchmark/bench/provenance.py:661) reconstructs `host:port`. This differs from the authority urllib actually checks.

Reproduced without network traffic, using a matching fake router:

```text
MLX_SERVE_BASE=http://localhost:08000
http_proxy=http://proxy.example:8888
no_proxy=localhost:8000

Guard:                ACCEPT pid=123, port=8000
urllib ProxyHandler:  destination=proxy.example:8888
```

Also reproduced with:

- `http://localhost` and `no_proxy=localhost:80`.
- `http://[::1]:8000` and `no_proxy=::1`.

All three accept local-router attribution while urllib routes through the proxy. The client preserves the supplied URL at [client.py:21]($STACK_REPO/benchmark/bench/client.py:21).

**Fix:** use the transport’s actual request authority for bypass matching, preserving IPv6 brackets, port spelling, and explicit versus omitted ports. Add differential tests against `urllib.request.ProxyHandler`. No separate new hardening findings.

**P36 — Acceptance and regression assessment**

| Criterion | Result | Evidence |
|---|---|---|
| A1 — Ordering/refusal outputs | PASS | Entry tests pass; guard precedes precheck at [generate.py:450]($STACK_REPO/benchmark/bench/generate.py:450). |
| A2 — Config resolution | PASS | Router cwd/HOME, existence and symlink tests pass; [provenance.py:755]($STACK_REPO/benchmark/bench/provenance.py:755). |
| A3 — Destination ownership | **FAIL** | P35 permits traffic through an unverified proxy. |
| A4 — Accurate attribution | **FAIL** | Storage/history tests pass, but P35 supplies false attribution to [provenance.py:1123]($STACK_REPO/benchmark/bench/provenance.py:1123). |
| A5 — Test adequacy | **FAIL** | P32/P33 regressions pass; authority-versus-transport cases remain uncovered. |
| A6 — Original incident | PASS | Overlay mismatch test passes at [test_provenance_fingerprint.py:488]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:488). |
| A7 — Exceptions/discovery/API | PASS | Discovery and fatal restart/refresh tests pass; [generate.py:303]($STACK_REPO/benchmark/bench/generate.py:303). |

**257 focused/regression tests passed**, with opencode config resolution stubbed during the test run. `git diff --check` passed. Repository files remained unchanged; temporary tests stayed under `STACK_WORKDIR`. No model requests were sent. Previously declined items remain declined.
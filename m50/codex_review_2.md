VERDICT: FAIL

The stable overlay-driver versus daily-driver-on-`:8000` incident now refuses at every reviewed entry point. However, opencode configuration overrides and failed restart verification can still bypass the intended protection.

| Finding | Round-2 assessment |
|---|---|
| **P1 / F1** | **CONFIRMED-FIXED.** CLI guard precedes `_resolve` at [run.py:126]($STACK_REPO/benchmark/run.py:126); direct callers remain guarded at [generate.py:441]($STACK_REPO/benchmark/bench/generate.py:441). |
| **P2 / F2** | **CONFIRMED-FIXED** for directory creation: [stack_smoke.py:176]($STACK_REPO/benchmark/bench/stack_smoke.py:176), [parity_replay.py:66]($STACK_REPO/benchmark/bench/parity_replay.py:66), [session_cache_probe.py:351]($STACK_REPO/benchmark/bench/session_cache_probe.py:351). The nonexistent-parent test passes. “First action” overstates smoke’s ordering: `params_for` still runs before verification. |
| **P3 / F3** | **CONFIRMED-FIXED.** Router HOME expansion, refusal of `~user`, and refusal of relative paths without router cwd are implemented at [provenance.py:635]($STACK_REPO/benchmark/bench/provenance.py:635). |
| **P4 / F4** | **CONFIRMED-FIXED.** Existing-file requirement at [provenance.py:651]($STACK_REPO/benchmark/bench/provenance.py:651); absent-variable diagnostic at [provenance.py:697]($STACK_REPO/benchmark/bench/provenance.py:697). |
| **P5 / F5** | **NOT-FIXED completely — medium.** Remote hosts and multiple PIDs refuse, but [provenance.py:614]($STACK_REPO/benchmark/bench/provenance.py:614) discards bound addresses. Reproduced approval of `http://127.0.0.1:8000` using a sole `::1` listener. **Fix:** retain address/family information and require a listener covering the requested destination; refuse when that cannot be established. |
| **P6 / F6** | **NOT-FIXED — blocker.** Both callers use the new resolver, but [provenance.py:727]($STACK_REPO/benchmark/bench/provenance.py:727) reads only global JSON or the shipped file—not opencode’s effective configuration. See P14. |
| **P7 / F7** | **NOT-FIXED — major.** [provenance.py:689]($STACK_REPO/benchmark/bench/provenance.py:689) tests substrings in the entire command line. Reproduced acceptance of `/opt/mlx-serve/.venv/bin/python -m http.server 8000`. **Fix:** inspect argv structure and validate the actual router executable/module and invocation, rather than a directory-name substring. |
| **P8 / F8** | **NOT-FIXED completely — major/privacy.** Repeated occurrences of the **driver’s** HOME are scrubbed, but [provenance.py:662]($STACK_REPO/benchmark/bench/provenance.py:662) ignores the router’s distinct HOME. Reproduced `/Users/router-other/...` surviving in the returned `cmdline`. **Fix:** sanitize both known homes consistently, including persisted diagnostics, or omit raw command lines. |
| **P9 / F9** | **CONFIRMED-FIXED for the accepted scope.** Abort records include router at [stack_smoke.py:191]($STACK_REPO/benchmark/bench/stack_smoke.py:191) and [parity_replay.py:89]($STACK_REPO/benchmark/bench/parity_replay.py:89). Vision remains summary-only at [vision_gate.py:324]($STACK_REPO/benchmark/vision_gate.py:324); interruption before summary remains the explicitly declined gap. |
| **P10 / F10** | **CONFIRMED-FIXED for compatible generate resumes.** [generate.py:270]($STACK_REPO/benchmark/bench/generate.py:270) invokes `_refresh_router`; [generate.py:283]($STACK_REPO/benchmark/bench/generate.py:283) preserves previous different-PID blocks. In-process restart history remains missing; see P17. |
| **P11 / F11** | **CONFIRMED-FIXED for the claimed added coverage.** Real discovery functions are exercised at [test_provenance_fingerprint.py:614]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:614), including lsof parsing/union; entry-order, abort, restart-order and resume tests are present. These tests miss the integration failures below. |
| **P12 / F12** | **NOT-FIXED — blocker.** Verification occurs after restart at [generate.py:225]($STACK_REPO/benchmark/bench/generate.py:225), but its refusal is swallowed by the enclosing item-error handler. See P16. The explicitly accepted check/use window and deferred router-side hash are not additional blockers here. |
| **P13 / F13** | **CONFIRMED-FIXED.** Dependency floor at [requirements.txt:20]($STACK_REPO/benchmark/requirements.txt:20), legacy accessor fallback at [provenance.py:572]($STACK_REPO/benchmark/bench/provenance.py:572), independent fact reads at line 601, and cached manifest lookup at line 714. |

**P14 — NEW: opencode can override the verified destination — blocker, A3/A6.**

The resolver ignores `OPENCODE_CONFIG_CONTENT`, while [_opencode_env:271]($STACK_REPO/benchmark/run_opencode_probe.py:271) and [session_cache_probe.py:258]($STACK_REPO/benchmark/bench/session_cache_probe.py:258) inherit it. OpenCode documents inline configuration as overriding global configuration. [Configuration precedence](https://opencode.ai/docs/config/#precedence-order)

Reproduced: verification selects global `localhost:8123`, but the child receives an inline provider override selecting `localhost:8000`. This recreates the overlay-versus-daily-driver contamination.

**Fix:** resolve and bind the effective child configuration using its actual environment and working directory; reject unsupported overrides. Do not assume the shipped fallback is loaded unless the child is explicitly configured to load it.

**P15 — NEW: opencode manifests record the wrong endpoint — major, A4.**

[run_opencode_probe.py:563]($STACK_REPO/benchmark/run_opencode_probe.py:563) calls `gather`, which unconditionally selects `router_block(client.BASE)` at [provenance.py:941]($STACK_REPO/benchmark/bench/provenance.py:941). The verified `router` variable is never attached.

Reproduced: verified router cached under `8123`; resulting manifest contains `port: 8000, pid: null`. A matching listener on `8000` could instead stamp an unrelated PID.

**Fix:** pass the verified router block into manifest assembly. Add a successful opencode-manifest test with differing URLs.

**P16 — NEW: failed restart verification becomes an ordinary error row — blocker, A6.**

The `RuntimeError` from post-restart verification reaches [generate.py:543]($STACK_REPO/benchmark/bench/generate.py:543), which records an error and continues.

Reproduced with real `run` and recovery control flow, mocked traffic:

```text
verify_entry → probe_initial → restart → verify_REFUSED
→ next_item_probe → restart → verify_REFUSED
→ COMPLETE
```

**Fix:** use a dedicated fatal tripwire exception and re-raise it before generic item-error handling. Test that refusal prevents every subsequent request and exits unsuccessfully.

**P17 — NEW: successful restarts leave manifests naming the old router — major, A4.**

[generate.py:459]($STACK_REPO/benchmark/bench/generate.py:459) stamps manifests once before the loop. Restart verification updates only the in-memory cache; no subsequent manifest refresh occurs. Later primary rows therefore retain the original PID without history.

**Fix:** refresh affected manifests and append router history after each successful restart, before further model traffic. Test the complete driver path, not only `router_block` in isolation.

**P18 — Acceptance retest:** A1 **PASS** for request/output ordering; A2 **PASS**; A3 **FAIL**; A4 **FAIL**; A5 **PASS-WITH-GAPS**; A6 **FAIL**; A7 **PASS**.

**P19 — Validation:** 78 focused pytest tests passed. Additional in-memory checks reproduced the failures above and confirmed all seven entry paths reject the stable incident before requests/output writes. `git diff --check` passed. No repository files were modified; pytest scratch stayed under `STACK_WORKDIR`. No live model requests or router restarts were performed.
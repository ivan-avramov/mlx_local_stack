I have completed the trace. Here are my findings.

## Design dispositions (`.review-material/design-dispositions.md`)

Every disposition is **resolved** as written:

- **Sol P1** (DECLINED waives harness FAILs, blocker, adapted): resolved. `p426_freeze.declinable_verify_verdict` accepts `not_observed*` or `FAIL:no_shell_part`; `declined_ok` requires the marker, an events sha256 and a declinable verify verdict; `decline_evidence` additionally enforces the V3 evidence-hash check and the marker-absence proof.
- **Sol P2 / GLM F4 / Sol P4 / Sol P5 / GLM F1 / GLM F2 / GLM F10 / GLM F12 / GLM F13 / GLM F14 / GLM F15**: resolved, each implemented at the cited location (`GenerationPolicy.gradle_user_home` omitted when None; `host_env_final` on both exits; cache-manifest size check; `try/except/finally` in `cmd_positives`; `try/except BaseException` around launch→`leg.json`; `class: systemic`; `"; ".join(diff)`; `agent_env` = policy fields + HOME/TMPDIR/GRADLE_USER_HOME; `(prior: …)`; baseline at `run()` entry; `host_env_after` recorded).
- **GLM F5 / GLM F6** (declined): resolved-as-declined; the spec records the JVM `user.home` fact and `build_env` sets `GRADLE_USER_HOME` for tg2.
- **GLM F7–F9** (noted): resolved; the spec governs.
- **GLM F11** (scope, kept): resolved; `host_env_final` is implemented.

---

## Findings

### F1 — `BoxSeqOps.inject_verify` returns the collapsed exit code, not the real verdict (blocker)

- **Location:** `benchmark/bench/p426_wave2.py` `BoxSeqOps.inject_verify` / `inject_verify_result` (diff lines ~577–583).
- **Severity:** blocker.
- **Evidence:** confirmed. `inject_verify` returns `self.inject_verify_result(run, kind)["verdict"]`, and `inject_verify_result` builds `verdict="PASS" if done.returncode == 0 else f"FAIL (inject_verify rc {done.returncode})"`. For a `not_observed:kill` (rc 4) the public `inject_verify` returns the string `"FAIL (inject_verify rc 4)"`, not `"not_observed:kill"`.
- **Problem:** The frozen acceptance test `test_s26_frozen/test_s26_positives.py::test_fix_the_box_inject_verify_returns_the_real_verdict_not_a_bare_exit_code` calls `ops.inject_verify(res["run"], "loop")` over the real `m62/inject_verify.py` and asserts `"not_observed" in text and "inject_verify rc" not in text`. On the candidate both halves fail. The implementer's own `test_s26_impl_positives.py::test_the_box_inject_verify_keeps_its_string_and_reports_the_row_verdict` asserts the opposite (`== "FAIL (inject_verify rc 4)"`), so the two are in direct conflict and the frozen test loses.
- **Failure scenario:** Run the frozen positives suite on the candidate; the hybrid test above fails its assertion, so acceptance criterion 1 is not met even though the decline *logic* (which uses `inject_verify_result.row_verdict` via `_verify`) works. <!-- allow-shorthand -->
- **Proposed change:** Make `BoxSeqOps.inject_verify` return the retained attempt's verdict (`inject_verify_result(...)["row_verdict"]`), falling back tothe collapsed form only when parsing yielded `None`. For a PASS case the retained line is `PASS`, so `test_m76_b4b1_impl_wave2.py:294` (`== "PASS"`) still passes; update the implementer's own `test_the_box_inject_verify_keeps_its_string_and_reports_the_row_verdict` accordingly (it is not frozen).

### F2 — `main`'s `finally` republishes after a `host_env_final` Stop (minor)

- **Location:** `benchmark/bench/p426_wave2.py` `main` (lines ~1905–1909) vs `Sequencer.host_env_final` / `run` (lines ~1445–1457).
- **Severity:** minor.
- **Evidence:** confirmed. `host_env_final` raises `Stop(1)` before `publish_run_files_or_stop` on both exits, but `main`'s `finally` calls `seq.publish_run_files()` unconditionally; `run_files_done` is still False, so the files publish. The frozen test `test_fix_a_change_after_the_last_leg_is_caught_before_the_run_files_are_published` encodes this (asserts `r["ops"].publishes` non-empty with `host_env_after_last_leg` in each).
- **Problem:** Spec §2 says "no difference → publish, log, return as today", implying a difference does not publish; the implementation publishes anyway. The diff is recorded in `sequence.json` and rc is 1, so the operator is informed and the changed leg is INVALID/non-poolable, but a post-last-leg change still yields a published run whose (valid) legs remain poolable.
- **Failure scenario:** A detached installer changes the Cellar after the last leg; the run stops rc 1 but the run files are published with the diff recorded rather than withheld.
- **Proposed change:** Either accept this as consistent with existing Stop behaviour (power/OVERRUN stops also publish via the `finally`), or gate `main`'s `finally` on `not seq.host_env_after_last_leg` (a scope decision for the operator).

### F3 — Host-changed INVALID leg stops even where INVALID is expected (rehearsal R2) (minor)

- **Location:** `benchmark/bench/p426_wave2.py` `Sequencer.after_leg` (diff lines ~1259–1264).
- **Severity:** minor (hypothesis — not traced through a real R2-with-host-change; untested).
- **Evidence:** confirmed in source. `after_leg` raises `Stop(1, "STOP: … is INVALID: <reason> (a rerun is an operator decision)")` whenever `entry["reason"]` starts with `HOST_ENV_REASON`, before the `if entry["state"] == spec["expect"]: return` branch that lets an expected INVALID leg continue.
- **Problem:** Spec §2 says a host-changed leg "is harvested as INVALID legs are; the run stops as for any INVALID leg." In rehearsal R2 an INVALID leg is *expected* and the run continues; the candidate overrides that for host changes (implementer deviation P6). No frozen test covers R2 + host change.
- **Failure scenario:** An R2 rehearsal leg that also happens to change the host stops the rehearsal with a host-change Stop instead of completing as the rehearsal expects.
- **Proposed change:** Drop the special-case `Stop` in `after_leg` and let a host-changed INVALID leg follow the same path as any INVALID leg (stop on unexpected, continue on expected), keeping the host-change reason in `leg.json`/`sequence.json`.

### F4 — `fingerprint` records an extra `path` section beyond the spec's interface (scope request)

- **Location:** `benchmark/bench/host_env.py` `fingerprint` (line ~163, `out = {"path": path}`) and `diff` (line ~237).
- **Severity:** scope request (no material consequence).
- **Evidence:** confirmed. Spec §1 lists sections `tools, cellar, bin_dirs, npm_global, home_toolchains, files`; the candidate adds `path` (the agent PATH string) and diffs it. The frozen test `test_new_fingerprint_is_deterministic_json_and_has_every_section` uses `<=` (subset), so it tolerates the extra key.
- **Problem:** Beyond the spec's stated interface; harmless (the PATH is `/opt/homebrew/bin:/usr/bin:/bin`, no PII) and the diff message is useful, but it is an undocumented field that future consumers must not rely on.
- **Proposed change:** Either document `path` in the spec's §1 interface, or drop it from the fingerprint (keep it only as the `path=` parameter).

### F5 — Test gaps (minor)

- **Location:** `benchmark/bench/tests/s26_frozen/`.
- **Severity:** minor.
- **Evidence:** confirmed by reading the frozen tests and the testwriter report (P8, P9).
- **Problem:** (a) The B4b-1 tg1 golden (`test_m76_b4b1_impl_golden_tg1.py`) is explicitly Phase B and not run; tg1 byte-identity is only checked via the policy-hash and env-equality invariants, not the full golden. (b) The sequencer is tested only on the tg1 (`mtp`) path; the tg2/kv path shares `Sequencer.run` but has no separate test (testwriter P8). (c) `scripts/bootstrap_machine.sh` step 5b is untested (testwriter P9, implementer P10). (d) The `portable` PII scrubbing of exception messages in `cmd_positives` is untested (the 300-char test uses a message with no home path).
- **Failure scenario:** A regression in the tg2/kv sequencer host-guard path, or a broken bootstrap step 5b, is not caught by the frozen suite.
- **Proposed change:** Add a tg2/kv sequencer host-guard test, a `bash -n` (and ideally a mocked `brew`) test for step 5b, and an exception-message test that includes a home path to exercise `portable`; run the B4b-1 golden as Phase B.

---

## Summary of the four questions

- **What fails in use:** F1 — the frozen hybrid test `test_fix_the_box_inject_verify_returns_the_real_verdict_not_a_bare_exit_code` fails on the candidate because `BoxSeqOps.inject_verify` still collapses non-zero exits to `FAIL (inject_verify rc N)`. The decline *logic* itself works (it uses `inject_verify_result.row_verdict`), so the spec's purpose is met, but acceptance criterion 1 is not.
- **What the tests miss:** F5 — tg2/kv sequencer path, bootstrap step 5b, `portable` PII scrubbing, and the B4b-1 golden (Phase B).
- **Beyond the spec:** F4 (`path` section in the fingerprint) and F3 (host-changed INVALID stops even in R2).
- **tg1 byte-identical:** Yes, by code trace — `gradle_home` is None for tg1, every tg2-gated branch (`build_env`, `identity`, `_identity_inputs`, `--print-identity`) is skipped, and `GenerationPolicy.gradle_user_home` is omitted from `as_dict()`/the hash when None, so `scaffold_policy_sha256` is unchanged. `probe_code_sha256` rotates (expected by C178; the golden's `test_closure_identity_fields_rotate` asserts this). `host_env`/`tg2_gradle_home` are imported only by the sequencer and via `importlib` inside `arm_opencode`, so they do not enter the probe closure.
- **Can a host change escape / a harness failure be recorded as a decline:** A host change escapes only in the spec's stated non-goal areas (contents of already-present `~/.gradle`/`~/.cargo`, uncovered locations); the covered sections (tools, Cellar, bin_dirs, npm_global, home toolchains, the tg2 `gradle.properties` file) are all diffed. A harness failure is **not** recorded as a model decline: `decline_evidence` requires the events to contain no tool call carrying the marker (proof the model did not run it), the row's sha to match, and the evidence hashes to verify; a transport abort, missing/tampered row, unreadable events, or a non-declinable verdict all leave the verdict as the failure. The one residual is F1's converse: a real decline could be mis-recorded as a failure if `decline_evidence` itself raises an unexpected exception, but that fails the run conservatively (never falsely passes).

P1 — Design Sol P1: NOT RESOLVED  
- Location: `benchmark/m62/inject_verify.py:240-253`; `benchmark/bench/p426_wave2.py:193-236`; `benchmark/bench/p426_freeze.py:76-88`
- Severity: blocker
- Evidence: confirmed by source trace.
- Problem: `FAIL:no_shell_part` already means a model-owned process containing `bytearray(` exceeded the RSS threshold, but its tool event is missing. The candidate then treats that missing event—and therefore missing marker—as proof of decline.
- Failure scenario: the model runs the allocation, ProcessGuard kills it, but opencode omits the tool event. Positives records `DECLINED` and passes a harness-evidence failure.
- Proposed change: only permit `not_observed*` as DECLINED. Keep every `FAIL:*`, including `FAIL:no_shell_part`, as FAIL.

P2 — Design Sol P2: RESOLVED  
- Location: `benchmark/bench/run_config.py:70-179`; `benchmark/bench/arm_runner.py:937-959`
- Severity: major
- Evidence: confirmed.
- Problem: resolved: `gradle_user_home` is rebuilt through `GenerationPolicy` and omitted when `None`.
- Failure scenario: none for the original finding; tg1’s policy dictionary and `scaffold_policy_sha256` remain unchanged.
- Proposed change: none. Entire tg1 identity is not byte-identical; see P22.

P3 — Design Sol P3 / GLM F4: RESOLVED  
- Location: `benchmark/bench/p426_wave2.py:839-846,1446-1455`
- Severity: major
- Evidence: confirmed.
- Problem: both DONE and `--through` paths check the host before normal publication.
- Failure scenario: a post-harvest change is saved in `host_env_after_last_leg` and stops the command.
- Proposed change: none.

P4 — Design Sol P4: RESOLVED  
- Location: `benchmark/bench/tg2_gradle_home.py:70-82,196-244`
- Severity: major
- Evidence: confirmed.
- Problem: recorded cache paths and sizes are checked against the live folder.
- Failure scenario: a missing or resized recorded dependency refuses the item.
- Proposed change: none within the reviewed light design.

P5 — Design Sol P5 / GLM F3: RESOLVED  
- Location: `benchmark/bench/p426_wave2.py:311-345`
- Severity: major
- Evidence: confirmed.
- Problem: grade, session and inject exceptions produce a sealed FAIL record containing both host fingerprints.
- Failure scenario: an inject changes Homebrew and raises; both facts are retained.
- Proposed change: none.

P6 — Design GLM F1: RESOLVED  
- Location: `benchmark/bench/p426_wave2.py:971-1005`
- Severity: major
- Evidence: confirmed.
- Problem: exceptions from launch through `leg.json` trigger a host comparison, logging and unchanged re-raise.
- Failure scenario: classification raises after a host mutation; the mutation is logged and the original exception propagates.
- Proposed change: none.

P7 — Design GLM F2: RESOLVED  
- Location: `benchmark/bench/p426_wave2.py:983-1009`
- Severity: major
- Evidence: confirmed.
- Problem: a host-changed leg becomes `INVALID`, class `systemic`, with its reason persisted.
- Failure scenario: `brew install` during an otherwise-valid leg invalidates and stops it.
- Proposed change: none.

P8 — Design GLM F5: RESOLVED  
- Location: `benchmark/bench/p426_wave2.py:1666-1683` → `benchmark/bench/tg2_runner.py:30-33` → `benchmark/bench/arm_runner.py:1122-1133,1200-1215`
- Severity: major
- Evidence: confirmed by call-chain trace.
- Problem: positives do reach `OpencodeArm.build_env`; their agent shell receives `GRADLE_USER_HOME`.
- Failure scenario: none remaining.
- Proposed change: none.

P9 — Design GLM F6: RESOLVED  
- Location: `benchmark/bench/arm_opencode.py:450-459`
- Severity: major
- Evidence: confirmed.
- Problem: explicit `GRADLE_USER_HOME` avoids dependence on JVM `user.home`.
- Failure scenario: Gradle no longer defaults to the operator’s real `~/.gradle`.
- Proposed change: none.

P10 — Design GLM F7–F9: RESOLVED  
- Location: `benchmark/bench/host_env.py`; `benchmark/bench/tg2_gradle_home.py`
- Severity: minor
- Evidence: confirmed.
- Problem: fingerprinting hashes binaries without running them and includes files, npm globals and `Library/Python`.
- Failure scenario: none remaining.
- Proposed change: none.

P11 — Design GLM F10: RESOLVED  
- Location: `benchmark/bench/p426_wave2.py:796-799,839-846,983-987`
- Severity: minor
- Evidence: confirmed.
- Problem: differences use the specified `"; ".join(...)`.
- Failure scenario: none.
- Proposed change: none.

P12 — Design GLM F11: RESOLVED SCOPE REQUEST  
- Location: `benchmark/bench/p426_wave2.py:839-846`
- Evidence: confirmed.
- Problem: the retained final check catches detached changes after the last leg check.
- Failure scenario: a late installer is detected before success.
- Proposed change: none.

P13 — Design GLM F12: RESOLVED  
- Location: `benchmark/bench/tg2_gradle_home.py:84-89,151-175`
- Severity: minor
- Evidence: confirmed.
- Problem: prefill uses the scaffold policy plus only scratch `HOME`, scratch `TMPDIR` and `GRADLE_USER_HOME`.
- Failure scenario: operator environment variables do not leak into prefill.
- Proposed change: none.

P14 — Design GLM F13: RESOLVED  
- Location: `benchmark/bench/p426_wave2.py:983-987`
- Severity: minor
- Evidence: confirmed.
- Problem: the prior leg reason is retained as `(prior: …)`.
- Failure scenario: chain invalidity and host mutation remain distinguishable.
- Proposed change: none.

P15 — Design GLM F14: RESOLVED  
- Location: `benchmark/bench/p426_wave2.py:801-813,1429-1436`
- Severity: minor
- Evidence: confirmed.
- Problem: baseline creation/comparison occurs before any leg launch.
- Failure scenario: a resumed changed host refuses without launching.
- Proposed change: none.

P16 — Design GLM F15: RESOLVED  
- Location: `benchmark/bench/p426_wave2.py:337-342`
- Severity: minor
- Evidence: confirmed.
- Problem: positives record `host_env` and `host_env_after`.
- Failure scenario: none.
- Proposed change: none.

P17 — Nonzero probe exits can become model declines  
- Location: `benchmark/bench/p426_wave2.py:264-285,1687-1691`; `benchmark/bench/arm_runner.py:1289-1335`
- Severity: major
- Evidence: confirmed.
- Problem: when the probe exits nonzero but leaves a row, `positive_inject` may set `transport_abort=False`. `positive_entry` ignores `rc`, while `decline_evidence` skips row-hash validation when `row_sha256` is absent.
- Failure scenario: exit-time served-config drift raises after writing the row. A `not_observed` verdict is then sealed as DECLINED despite the provenance-invalid probe exit.
- Proposed change: require probe rc 0 and a valid `row_sha256` for PASS or DECLINED; otherwise record a probe/harness failure.

P18 — Gradle guard code is outside tg2 generation identity  
- Location: `benchmark/bench/arm_opencode.py:57-60,125-129,355-359`
- Severity: major
- Evidence: confirmed.
- Problem: `tg2_gradle_home` is dynamically imported and absent from `TG2_GENERATION_DATA`, so changes to its launch checks do not rotate `probe_code_sha256`.
- Failure scenario: weakening `check_problems()` to accept a damaged cache produces behaviorally different tg2 rows under the same probe-code identity.
- Proposed change: add `benchmark/bench/tg2_gradle_home.py` to `TG2_GENERATION_DATA` or bind it statically from the tg2-only entry.

P19 — Frozen verifier-interface test fails  
- Location: `benchmark/bench/p426_wave2.py:1693-1705`; `benchmark/bench/tests/s26_frozen/test_s26_positives.py:413-420`
- Severity: minor
- Evidence: confirmed by source comparison.
- Problem: `inject_verify()` returns `FAIL (inject_verify rc 4)` rather than the parsed `not_observed*` verdict required by the frozen test.
- Failure scenario: the frozen hybrid decline test fails despite `cmd_positives` using the separate richer method.
- Proposed change: return `row_verdict` from `inject_verify()` and retain rc/result metadata in `inject_verify_result()`.

P20 — Frozen host-seam test fails  
- Location: `benchmark/bench/p426_wave2.py:1545-1549`; `benchmark/bench/tests/s26_frozen/test_s26_sequencer.py:278-287`
- Severity: minor
- Evidence: confirmed.
- Problem: `BoxSeqOps.host_env()` passes `workdir=...`, while the specified seam test replaces `fingerprint_for_run` with a zero-argument callable.
- Failure scenario: the test raises `TypeError` instead of returning its sentinel.
- Proposed change: call `fingerprint_for_run()` without arguments; real execution already resolves `STACK_WORKDIR`.

P21 — Candidate adds an unsupported PREFILL seal requirement  
- Location: `benchmark/bench/tg2_gradle_home.py:213-219`; `benchmark/bench/tests/s26_frozen/test_s26_arm_identity.py:179-186`
- Severity: minor
- Evidence: confirmed.
- Problem: the specification requires checking enumerated facts, not an intact self-seal. The candidate additionally requires `ph.sealed_ok`.
- Failure scenario: the frozen test changes only informational `created`; required facts remain valid, but `check()` refuses instead of allowing identity to rotate.
- Proposed change: remove the seal requirement or amend the specification and frozen test explicitly.

P22 — tg1 is not literally byte-identical  
- Location: `benchmark/bench/arm_opencode.py`; `benchmark/bench/arm_runner.py`; `benchmark/bench/run_config.py`; `benchmark/bench/p426_wave2.py`
- Severity: minor
- Evidence: confirmed.
- Problem: tg1 agent env, argv and scaffold-policy hash remain unchanged, but its closure-derived `probe_code_sha256` rotates. The Wave 2 sequencer also intentionally gains host checks, `host_env.json` and new failure records.
- Failure scenario: any consumer comparing the entire tg1 identity or sequencer output byte-for-byte observes a change.
- Proposed change: clarify the constraint as “tg1 probe env, argv and scaffold policy unchanged; closure identity rotates; sequencer gains the requested guard.”

P23 — Host mutations can escape the snapshot  
- Location: `benchmark/bench/host_env.py:79-173`; `benchmark/bench/tg2_gradle_home.py:70-82,231-243`
- Scope request — no severity.
- Evidence: confirmed.
- Problem: persistent enumerated changes are caught, but contents of existing home-toolchain directories, in-place non-tool Cellar files, equal-size Gradle-cache rewrites, and mutate-then-restore activity between snapshots are not.
- Failure scenario: an agent rewrites an existing dependency JAR with equal-size bytes; neither the host fingerprint nor cache-size check notices.
- Proposed change: only if scope expands, hash selected shared-cache and existing-toolchain contents. The current light design explicitly accepts incomplete coverage.

P24 — Candidate adds unreviewed schema/interface surface  
- Location: `benchmark/bench/host_env.py:23,157-173`; `benchmark/bench/tg2_gradle_home.py:176-181`; `benchmark/bench/arm_opencode.py:242-259`
- Severity: minor
- Evidence: confirmed.
- Problem: beyond the specification, the fingerprint adds a `path` section; `PREFILL.json` adds `kind`, `path`, `properties`, `stop_rc` and errors; and `OpencodeArm` gains injectable `gradle_home`.
- Failure scenario: consumers expecting the specified fingerprint shape or receipt validation semantics encounter additional fields/constraints.
- Proposed change: document these extensions; remove only those without a concrete consumer.

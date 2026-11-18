P1
- Location: `docs/specs/s26-agent-env.md` §4, lines 93–99.
- Severity: blocker.
- Evidence: confirmed — `inject_verify.verify_row` returns hard `FAIL:*` verdicts independently of marker presence; the observed Java alloc case was `FAIL:no_shell_part`.
- Problem: every non-PASS result with no marker becomes `DECLINED`, including corrupted evidence, malformed rows, worker drift, or failed causal linkage. This waives harness failures, not merely model refusal.
- Concrete failure scenario: alloc produces a memory kill but no corresponding event, yielding `FAIL:no_shell_part`; because the events lack `bytearray(`, the specification records `DECLINED` and the positives pass.
- Proposed change: permit `DECLINED` only for an explicit retained `not_observed*` verifier verdict, intact/hash-verified evidence, no marker, and recorded model refusal. Never downgrade `FAIL:*`, `competing_trigger:*`, or transport failures. Require `positives_problems` to validate the declined evidence.

P2
- Location: §3 lines 87–90 and Scope; `benchmark/bench/arm_runner.py:937–957`; `benchmark/bench/run_config.py:70–174`.
- Severity: major.
- Evidence: confirmed — `_identity_inputs` rebuilds and replaces the adapter policy using `GenerationPolicy`, whose schema has no `gradle_user_home` field. It then overwrites `scaffold_policy_sha256`.
- Problem: adding `policy["gradle_user_home"]` only in `OpencodeArm.identity` does not reach the live tg2 `--print-identity`. The files required to carry it are outside scope.
- Concrete failure scenario: a unit test of `OpencodeArm.identity` passes, but `BoxOps.identity()` receives a policy hash that excludes the Gradle path and receipt hashes.
- Proposed change: add `arm_runner.py` and `run_config.py` to scope; carry an optional Gradle policy through `GenerationPolicy` and `_identity_inputs`, omitting it entirely for tg1. Test the real tg2 `--print-identity` path.

P3
- Location: §2 lines 67–69; `Sequencer.run` at `benchmark/bench/p426_wave2.py:1203–1227`.
- Severity: major.
- Evidence: confirmed — the full path publishes before logging `DONE`; the `--through` path publishes and returns separately.
- Problem: “after the last leg (the DONE path)” neither defines ordering before publication nor covers `--through`.
- Concrete failure scenario: final-leg harvesting or dossier work changes the host after the post-supervision check. A literal implementation checks after publication—or omits the check under `--through`—so clean run files are published before the drift is recorded.
- Proposed change: define one finalization path used by both normal and `--through`: fingerprint, save `host_env_after_last_leg` on drift, then publish, then return/log success.

P4
- Location: §3 lines 78–90.
- Severity: major.
- Evidence: confirmed — `check` validates only properties and claims recorded in `PREFILL.json`; the host fingerprint hashes only `gradle.properties`, not cached artifacts.
- Problem: the check does not establish that the cache still exists or serves every valid Java item offline. It also does not explicitly require an exact valid-item set.
- Concrete failure scenario: dependencies or the Gradle 8.7 distribution are deleted while `PREFILL.json` remains. `build_env` accepts the folder, and the first Java item downloads them over the open network.
- Proposed change: make the receipt cover the exact valid-Java item set and a deterministic cache manifest, and verify it before a tg2 session/leg; alternatively rerun an offline resolution preflight. Specify that `--force` clears and recreates the folder.

P5
- Location: §2 lines 70–72, `cmd_positives`.
- Severity: minor.
- Evidence: confirmed — current record construction occurs only after `positives_session` exits.
- Problem: the specification requires a post-check in `finally` when an inject raises, while also saying drift is added to `problems` and carried in the sealed record. It does not define whether the exception is converted, re-raised, or recorded.
- Concrete failure scenario: an inject changes Homebrew and then raises; drift is detected in `finally`, but no positives record can be produced under the current control flow.
- Proposed change: explicitly require catching the operational exception, sealing a FAIL record with its type and host diff, then returning nonzero; or state that no record is expected and require the diff in stderr.

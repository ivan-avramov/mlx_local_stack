I've implemented the spec in Phase A. No test has been run yet. The only shell commands were `py_compile` syntax checks, all clean, plus `wc -l`, `git status --short` and `git diff --stat`/`git diff` for inspection. I didn't commit, push or touch `.git`, and no command or search pattern contained any of the forbidden strings.

**Files**
- added `benchmark/bench/host_env.py`: `fingerprint`, `diff`, `fingerprint_for_run`, `portable`.
- added `benchmark/bench/tg2_gradle_home.py`: `prefill`, `check`, `check_problems`, `identity_policy`, `committed_universe`, `cache_manifest`, and the CLI.
- changed `benchmark/bench/p426_wave2.py`:
  - host-env baseline at run entry, plus checks before launch, after each leg, on an exception and at both exits.
  - `host_env.json` is published with the run files.
  - positives restructured (one `try`, `env0`/`env1`, PASS / DECLINED / FAIL per kind).
  - new `BoxSeqOps.host_env` and `BoxSeqOps.inject_verify_result`.
- changed `benchmark/bench/p426_freeze.py`: `DECLINE_MARKERS`, `declinable_verify_verdict`, `declined_ok`; the v8 check accepts DECLINED for loop / alloc only.
- changed `benchmark/bench/arm_opencode.py`: tg2 `build_env` sets or refuses the Gradle home; tg2 identity and `--print-identity` carry the Gradle block.
- changed `benchmark/bench/arm_runner.py`: `_identity_inputs` passes `gradle_user_home` only when the adapter names it.
- changed `benchmark/bench/run_config.py`: `GenerationPolicy.gradle_user_home`, left out of `as_dict()` and the hash when None.
- changed `scripts/bootstrap_machine.sh`: step 5b.
- added tests `benchmark/bench/tests/test_s26_impl_{host_env,sequencer,positives,gradle}.py`.

**Deviations from the spec's interfaces, and gaps**

| id | What | Why |
|---|---|---|
| P1 | `arm_opencode` loads `tg2_gradle_home` by name (`importlib`), with an optional `gradle_home=` constructor argument, instead of a normal import. | The import-closure walker also follows imports inside functions. `test_p371_closures` forbids `tg2_*` and `schedules` modules in the tg1/oc probe closures, and `test_p311_closure` requires every closure module to be loaded by a tg1 run. `tg2_runner.py` is outside my scope. The cost: the module's code is not in tg2's `probe_code_sha256`; the policy hash still covers the folder's state. I recommend a one-line binding in `tg2_runner.py`; that needs your scope approval. |
| P2 | tg1's `scaffold_policy_sha256` is unchanged, but tg1's `probe_code_sha256` changes. | The spec requires edits to `arm_runner.py`, `run_config.py` and `arm_opencode.py`, which are in the tg1 closure. The B4b-1 golden expects that change (C178). Don't merge this into the arm worktrees while the current tg1 Wave 2 runs: its records pin the old value. |
| P3 | `BoxSeqOps.inject_verify` still returns a string; the new `inject_verify_result` returns the retained attempt's verdict and the RESULT line. | An existing test asserts `inject_verify(...) == "PASS"`. `cmd_positives` uses the new method when it exists. |
| P4 | The fingerprint also records the agent `path`, and writes the real home as `~`. | The home path would otherwise end up in published records (no-PII rule). Exception messages in positives problems are made portable the same way. |
| P5 | The exception path is `except BaseException: log the diff; re-raise` rather than a literal `finally`. | It behaves the same: on the normal path the comparison happens inside the region, before `leg.json` is written. |
| P6 | A host-change INVALID stops the run even where INVALID is expected (rehearsal R2). | Its reason is the host change, not the planted failure. Only these legs get a `reason` field in `sequence.json`. |
| P7 | After the end-of-run Stop, the existing `finally` in `main` still publishes the run files, as for any Stop. | The published `sequence.json` already contains `host_env_after_last_leg`. |
| P8 | A Refusal raised inside the positives (e.g. something already listening on :8000) now gives a sealed FAIL record instead of rc 2. | The spec says "any exception there". |
| P9 | `PREFILL.json` also records `kind`, `path`, `properties`, `stop_rc`, and an `error` for any item that couldn't be prepared; `check` also requires the record's own sha256 to verify. | — |
| P10 | Not done: a `bash -n` check of the bootstrap script, and acceptance criteria 2 and 3. | Only `py_compile` was allowed; nothing may run yet. |
| P11 | Unverified risk: `check` requires every recorded cache file to keep its exact size. | If Gradle rewrites lock or marker files under `wrapper/dists/`, items would be refused when nothing is wrong. Worth watching on the first real prefill. |

`test_s26_impl_gradle.py` has the path `benchmark/run_oc_probe.py` inside a Python string; it is read by the closure walker, never put on a command line. The tests reuse fixtures from `test_b2_s8_wave2.py`, `test_m76_b4b1_impl_wave2.py` and `test_p371_run_config.py`; none of those files were changed.
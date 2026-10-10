You are the implementer for one small, approved test-only repair in this repository (cwd = repo root). You have no prior context; everything needed is below. You may edit ONLY these files: `benchmark/bench/tests/test_opencode_probe_seeding.py`, `benchmark/bench/tests/test_scaffold_policy_compare.py`, `benchmark/bench/tests/test_run_agentbench_os.py`. Do not edit production code. No git commands that change state (no add/commit/stash/checkout/reset). A live model server owns localhost:8000 — never send it a request; do not start/stop servers or docker; do not run any real `opencode` binary.

## Problem 1 (20 red tests on main)
Run: `cd benchmark && ../.venv-bench/bin/python -m pytest bench/tests/test_opencode_probe_seeding.py bench/tests/test_scaffold_policy_compare.py -q -p no:cacheprovider`
19 tests in `test_opencode_probe_seeding.py` and `test_scaffold_policy_compare.py::test_clean_stale_never_deletes_legacy_opencode_rows` fail with messages like
`REFUSED: M50 cannot write the manifest …: M58: build_manifest needs a RESOLVED mtp_verify_scan in the runtime block (missing or 'unknown')` and
`ServingStateError: M58: mtp_verify_scan is UNRESOLVED for 'm' (model-not-in-registry)`.
Cause (already established): these tests drive `run_opencode_probe.main()` / provenance with a fake model name (`--model m`) that is not an entry of the registry (`main_models.yaml`), so `benchmark/bench/provenance.py::registry_mtp_verify_scan` returns "unknown" and the manifest guard added later (M58) correctly refuses. The guard is right; the test fixtures predate it. Two branches were each green and the merged tree was never run.

Required fix:
1. Make the fake-model tests resolve the scan at the NARROWEST seam that keeps the production guard intact — e.g. a shared fixture that monkeypatches `provenance.registry_mtp_verify_scan` to return `{"mtp_verify_scan": "per_query", "mtp_verify_scan_source": "registry"}` for the fake model only (delegating to the real function for any other model), or an equivalent approach you judge cleaner after reading how `_runtime_block` / `_resolve_control` work. Do not weaken or bypass `build_manifest`'s refusal, and do not delete or loosen any existing assertion.
2. Add ONE golden test against the REAL registry (the repo's `main_models.yaml`, resolved the way the code resolves it) for the real model name `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: the manifest runtime block produced through the same code path the probe uses records `mtp_verify_scan == "joint_v1"` with source `registry`. It must be deterministic regardless of what is running on the box: `registry_mtp_verify_scan` consults a live-worker lookup by default (`worker_lookup=_DEFAULT_LOOKUP`) and a real worker IS running on this machine — make sure the test controls that lookup (no worker found) rather than reading real processes.
3. Add ONE negative test proving the guard still fires: with the fake model and WITHOUT the fixture's stub, the manifest path refuses with the M58 message.

## Problem 2 (4 environment-dependent failures)
With `TMPDIR` set to a directory UNDER `$STACK_WORKDIR`, four tests in `benchmark/bench/tests/test_run_agentbench_os.py` fail: `test_resume_reuses_the_same_run_id_transcripts_dir_P29`, `test_resume_does_not_rewrite_an_existing_transcript`, `test_manifest_records_transcripts_dir`, `test_transcripts_dir_defaults_to_stack_workdir_m54_transcripts_model`. They pass with the default TMPDIR. Reported mechanism (verify it): portable-path encoding uses one workdir resolver (`resolve_stack_workdir`) while decoding uses a separately monkeypatched one (`stack_workdir`), so path components are duplicated when the temp dir is inside the real workdir. Fix the FIXTURE so both resolvers agree; no production change. Reproduce first: `STACK_WORKDIR` is defined in `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh`; run those four tests with `TMPDIR=$STACK_WORKDIR/c128/tmp` (exists, writable) and with the default.

## Done means
- `cd benchmark && ../.venv-bench/bin/python -m pytest bench/tests/test_opencode_probe_seeding.py bench/tests/test_scaffold_policy_compare.py bench/tests/test_run_agentbench_os.py -q -p no:cacheprovider` → 0 failures with the default TMPDIR, and the four Problem-2 tests also pass with `TMPDIR=$STACK_WORKDIR/c128/tmp`.
- Never interrupt a pytest run mid-flight (some tests use real ptys).
- No PII, absolute home paths, hostnames or login names in test code. Match the files' existing style.

## Report (final message, terse)
What you changed and why (per file), the exact pytest summary lines before and after, any test you could not make pass and why, anything in this brief that turned out wrong, and what you verified by running vs inferred.

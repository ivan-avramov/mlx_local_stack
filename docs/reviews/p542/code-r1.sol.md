P1
- Location: `dev/p369_phase2/qualify.py:944-1000,1054-1055,1119-1148`
- Severity: blocker
- Evidence: confirmed
- Problem: Arm selection and P369 gating use the registry read before locking/preflight, but execution serves a second registry read without verifying they match.
- Scenario: The first read shows an entry OFF, so no summary is required. Before preflight, the registry changes to a clean ON version. The second read is accepted and MTP-ON runs under the stale `served_off` arm without a P369 PASS.
- Proposed change: Under the lock, read the registry once and use those exact bytes for arm selection, gating, hashing, and execution; alternatively refuse unless the later bytes and stack HEAD exactly match the gated snapshot.

P2
- Location: `dev/p369_phase2/qualify.py:1122-1138,1347`
- Severity: major
- Evidence: confirmed
- Problem: Registry names are used directly in filesystem paths despite accepting any `models[].name`.
- Scenario: An MTP candidate named `vendor/model` with `--predictor off` attempts to write `out/mtp-off-vendor/model.yaml`; the missing intermediate directory causes `FileNotFoundError`. An absolute OFF entry name also makes `out / name` escape `--out`.
- Proposed change: Use an index or hash-derived filesystem identifier and verify every resolved output path remains beneath `--out`.

P3
- Location: `dev/p369_phase2/qualify.py:98-113`
- Severity: major
- Evidence: confirmed
- Problem: `mtp_off_registry` only recognizes unquoted MTP keys at exactly two spaces beyond the sequence item, although strict YAML parsing permits other valid forms.
- Scenario: A committed entry containing `"draft_kind": mtp` is recognized as MTP-ON but its OFF arm refuses because the regex removes nothing.
- Proposed change: Locate top-level mapping keys through YAML node marks, then remove their complete source lines while retaining the existing semantic equality guard.

P4
- Location: `mlx_vlm/tests/test_p542_qualify_any.py`, `test_c6_the_final_state_carries_rates_and_arm_per_entry`
- Severity: minor
- Evidence: confirmed
- Problem: The test only checks completed entries, while v1.1 requires rates whenever a record exists, including failed entries.
- Scenario: Moving `rates` into the success-only branch would violate the requirement while this test still passes.
- Proposed change: Inject a post-record validation failure and assert the FAILED state still contains `arm` and `rates`.

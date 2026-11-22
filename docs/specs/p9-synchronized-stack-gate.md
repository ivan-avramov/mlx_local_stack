# P9 — frozen stack gate fixtures

The dependency sync must leave historical benchmark evidence attributable to its recorded builds while allowing stack main to move to newly verified dependency pins. On the prior candidate, five tests failed because historical setup read live fork files or a live index expectation still held the old pins. The published tests also needed authentic historical registry bytes and their declared Python and Docker environment.

## Scope

- Keep B2 historical BASE_GITLINKS, runner hashes, manifests, and frozen arm evidence. Update the explicitly live LIVE_GITLINKS assertion in the eventual pin commit to exactly the new gated pair. That pin update belongs to the driver after both published fork SHAs are known.
- T3's S2 test fixture reads the actual historical fork tree at `1c7c8fa166582ac1a1c23ae9063527b2b5215b11`. Introduce `s2_inputs()` in `benchmark/bench/tests/t3_frozen_support.py`, returning verbatim decoded `(dev/ci.py, .upstream-sync-ref)` from that commit in the checked submodule's Git object store. Both `s2_layout` and `test_audits_and_ref_are_derived_per_sha_not_from_the_live_tree` use it. Missing objects or paths fail the fixture. The query reads Git objects without checkout, a remote request or a live-file fallback.
- The M76 B3 MTP golden uses the already-published byte-identical S2 registries. Add `_frozen_registry_text(frozen, arm)` in `benchmark/bench/tests/test_m76_b3_impl_golden_mtp.py`. For `off`, read `benchmark/bench/tests/fixtures/p426_off/main_models.yaml`. For `on`, read `benchmark/results/p426/wave1.s2/m1-p426s2-on-b1/m1/overlay-Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed.yaml`. Verify SHA-256 against `registry_off_sha` or `registry_on_sha` **before** decoding and exercising the existing checks. A wrong byte fails before any golden computation. Proven exact blobs are `98bfdee6ca37cd8444b8bb7daf190026a5a38535` and `13a9559cba870b627c5f4cbc4a71aba0e62fd4bd`. Preserve the manifest and all existing golden digests.
- Use the existing grader image and isolated managed CPython 3.12.15 for the full gate. Compare other previously failing tests against the new published base. Classify genuine remaining defects separately. Project code outside the named fixture paths stays outside this slice.
- Retain the eight-commit MLX-VLM follow-on sync and every existing publication guard. Verify the exact fork receipts under the current gate policy, publish the accepted fork before its stack pin, and gate the exact stack commit after the pins move.

## Acceptance

- T3 builds the S2 fixture from its original nine audits and `2ceff4c1` even with a newer live fork. Its historical, old-workflow and per-SHA assertions still pass.
- M76 leg checks and the pre-existing golden digest pass in an ordinary clone without the orphaned ON commit. The two source artifacts match the original frozen hash pair. Corrupting one artifact or its recorded digest fails the fixture.
- B2 keeps its recorded arms and validates the actual new live gitlinks when the stack pins move. The standard full gate and current pushed-base binding remain authoritative.

## Environment-specific fixture controls

The historical tg1 policy comparison uses the recorded grader image ID on both comparison sides. The ordinary identity still reads the actual grader, and live gate validation uses the actual image. This isolates the change to the inject allowlist while preserving the saved digest and its interpreter and lock inputs.

The exception-scrubbing test supplies a synthetic account home separate from its host fingerprint directories. It requires the precise redaction and the absence of that synthetic home from the sealed record.

The rebased P8 test receipt supplies its real fixture base for stack checks, satisfying the published protected-path binding while still checking exact exception scope. The protection and exception mechanisms are unchanged.

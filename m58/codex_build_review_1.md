**Verdicts:** fork **BLOCKING**; router **SHIP**; stack **BLOCKING**. These are build-review verdicts, not GPU qualification.

Paths below: `F` = `../mlx-vlm/mlx_vlm`; `R` = `../mlx-serve`; `S` = `.claude/worktrees/m58/benchmark/bench`. **VERIFIED** means source inspection or the explicitly described CPU probe.

- **B1 — HIGH, VERIFIED: replay can pass missing coverage.** `S/parity_replay.py:256–292` selects A’s expected keys instead of validating both sets; empty replays also succeed. Disk-free probes returned **0** for empty inputs and for a key required by B but absent from both row sets. **Fix:** require nonempty, unique, equal expected-key sets and exact row coverage; make legacy comparison explicitly nongating.

- **B2 — HIGH, VERIFIED: replay accepts invalid comparison provenance.** `S/parity_replay.py:149–165,229–267` resumes by key alone and compares neither payload hashes nor journal status. Changed payload hashes and two aborted journals both returned **0**. Missing identity fields can compare equal through `.get()`. **Fix:** validate resumed rows against frozen payload+seed hashes; require complete journals and mandatory identity fields; compare request hashes.

- **B3 — HIGH, VERIFIED: unresolved-control refusal does not cover every production path.** `S/provenance.py:887–903` refuses literal `unknown`, but `_runtime_block` at `1588–1609` does not. `generate` reaches that permissive path through manifest construction (`S/generate.py:321,459–475`); replay calls it directly (`S/parity_replay.py:187`). An unrecognized `joint_v2` also passed a direct `assert_serving_state` probe. **Fix:** centralize closed-set validation and invoke it before cleanup, manifest writes and requests, including after loading.

- **B4 — HIGH, VERIFIED: replay authentication is incomplete.** `S/parity_replay.py:172` calls `client.preload`; `S/client.py:40–44,80–83` sends no bearer header. Router auth covers that endpoint (`R/src/mlx_serve/router.py:65`). An authenticated run fails before reaching the newly authenticated completion request. **Fix:** authenticate preload through the same transport; test the whole run’s request sequence.

- **B5 — MEDIUM, VERIFIED: failure exits bypass C106.** `S/parity_replay.py:178–191,215–222` checks exit provenance only after successful completion. Transport/malformed-response aborts skip it; preload exceptions escape journaling entirely. **Fix:** put exit verification and drift recording in a failure-safe finalization path, preserving the original failure.

- **B6 — HIGH, VERIFIED: configured MTP can become non-MTP after the guard.** `F/server/generation.py:1444–1450` checks the configured kind; `1499–1514` subsequently replaces it with the resolved kind or `(None, None)`. The fallback is explicitly possible at `F/speculative/drafters/__init__.py:214–230`. **Fix:** additionally require a loaded MTP drafter after resolution/compatibility handling and before READY.

- **B7 — HIGH, VERIFIED: an invalid straddle result can satisfy the self-test.** `F/mtp_verify_scan.py:143–152` combines shape/dtype errors, non-finite values and bit differences into one flag. At `464–472`, any such flag satisfies the predicted known positive. Thus a finite identical 2048-key cell followed by NaNs at the straddle cell passes this check. **Fix:** always reject invalid shape/dtype/non-finite outputs; accept only a finite, representation-level difference as the known positive.

- **B8 — MEDIUM, VERIFIED: AB finalization misses exceptions.** `F/models/qwen3_5/speculative_verifier.py:406–417` calls `end_block()` only after `_model` returns. A disk-free execution of that method recorded **zero calls** on exception. Pending tensor references survive until a later snapshot/round (`F/mtp_verify_scan.py:276–291,326`). **Fix:** finalize or explicitly discard pending comparisons on every exit without replacing the original exception. Also, `_shadow` advances AB block counters before materialization (`274`), contrary to the stated ordering.

- **B9 — MEDIUM, VERIFIED code; conditional failure scenario: device selection is cached.** The new classifier calls the correct shared plan function with actual head counts (`F/mtp_verify_scan.py:238–242`), but that function reads the globally cached architecture suffix (`F/models/qwen3_5/language.py:492–495,528–533`). The separate domain check is live. **Fix:** make the shared mirror use live device information consistently. **ASSUMPTION:** stale architecture is reachable in deployment; I did not demonstrate it on this fixed-device worker.

- **B10 — MEDIUM, VERIFIED: threshold tests share an incorrect oracle.** `F/tests/test_mtp_verify_scan.py:66–80,216` replaces the production mirror and reuses that replacement as its oracle. At keys **1024/1025**, the real mirror returns **64/128 blocks**, while the stub returns **128/128**. Tests can miss the length-2 straddle at 1025. **Fix:** exercise the real mirror with only device discovery mocked, against independently specified threshold expectations.

- **B11 — MEDIUM, VERIFIED: AC8 does not prove the requested drafter identity.** `F/tests/test_mtp_verify_scan_generation.py:74–82` runs the drafter but discards its proposed tokens, substituting an oracle continuation. Target cache/RNG are reset and the same instances are reused; `_mtp_rounds` resets the drafter. However, assertions inspect target cache state, not the drafter’s final state, and hidden/cache arrays use `1e-4` (`140–150`). **Fix:** add an unmodified-drafter run and compare drafter state explicitly. CPU tolerance is reasonable numerical coverage, but does **not** satisfy literal exact AC8 or GPU identity.

- **B12 — MEDIUM, VERIFIED: the autouse provenance pin hides regressions.** `S/tests/conftest.py:87–107` converts **every** unresolved scan to `per_query`, not just specified fake models. A broken registry lookup can silently pass unrelated integration tests. **Fix:** pin explicit values in tests needing synthetic models; keep production refusal behavior active by default.

**Verified positives and limits**

- Bound **32**, causal-mask amendment, boolean-mask intersection, fallback dispatch and disjoint counters match the intended design (`F/mtp_verify_scan.py:192–271`). Unsupported shapes fail the load-time eligibility test. Missing `architecture` fails closed; it does not silently qualify.
- Default `_attention` is AST-identical to `main` after removing the new hook. This includes the shipped length-2 branch. Qualified length-2 straddles deliberately use per-query under `joint_v1`, as C120 requires. Default forward execution never calls the new policy; **load initialization still imports and resolves the new module**.
- Joint/reference calls use the same base SDPA entry, unchanged QKV objects, `cache` and `scale`; neither passes `policy` or `force_fused`. M57 therefore cannot observe these verifier calls (`F/mtp_verify_scan.py:107–136`; `F/models/base.py:435`).
- AB serves the production joint function’s output; uint16 representation comparison detects signed zero and non-finite values. One flag `mx.eval` occurs on the normal round path. **ASSUMPTION pending GPU qualification:** additional AB evaluation leaves downstream numerics unchanged.
- Cached-request counters are snapshotted and collected on the single generation thread (`F/server/generation.py:1795–1803,1954–1968,2603`). The verifier singleton owns no counters. The policy itself is **not independently thread-safe**.
- The 8 OpenAI/metrics plumbing sites and 2 Anthropic sites carry the field. Four direct default timing-serializer comparisons against `main` were byte-identical. This was not a full endpoint-byte comparison.
- Router validation/default commands are sound; `type == "vision"` correctly restricts the flags to the mlx-vlm worker.
- v7→v8 `per_query` compatibility passed; `joint_v1` was incompatible. Missing the new key alone does not make v7 rows stale; changed serving-code hashes can still do so.
- **Tests:** 10 selected router tests passed; 16 pure fingerprint tests passed with conftest disabled to avoid filesystem fixtures. Metadata-only executions of existing assertions killed both bound-36 and disabled-straddle mutations. Fork pytest was blocked at MLX import by unavailable Metal access; ordinary stack fixtures required forbidden temporary writes.
- Diff scope, markers, registry preservation and clean reviewed worktrees checked out. No local remote-tracking ref contains the reviewed tips. **ASSUMPTION:** nothing was pushed; local refs cannot prove remote state.

**Ten judgement-call rulings**

| Call | Ruling | Reason |
|---|---|---|
| 1 | ACCEPT | Disjoint route buckets; histogram only on fallback. |
| 2 | ACCEPT | Reason names are clear and sufficient. |
| 3 | ACCEPT | Nonempty contiguous boolean-mask restriction follows AC3; rare-path synchronization is explicit. |
| 4 | ACCEPT | Ragged-helper outputs remain outside this policy’s decision point. |
| 5 | ACCEPT | Explicit C120 requirement; default preserved. |
| 6 | **REJECT** | Must recheck resolved drafter; B6. |
| 7 | ACCEPT | Refusing unqualified shapes prevents a silently ineffective policy. |
| 8 | ACCEPT | Optional dictionary plus serializer flattening preserves default timing bytes. |
| 9 | ACCEPT | Completion-log extension is absent under default. |
| 10 | **REJECT as implemented** | Normal-path design is reasonable; exception cleanup and counter ordering fail B8. |

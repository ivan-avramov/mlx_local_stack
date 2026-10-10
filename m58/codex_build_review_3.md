**P1 — Verdicts at unchanged HEADs**

| Repo | HEAD | Verdict |
|---|---|---|
| Fork | `c0ab3270` | **FIX-THEN-SHIP** — acceptance-test and CI gaps |
| Router | `9b5d308` | **FIX-THEN-SHIP** — CI gap; command/config checks pass |
| Stack | `68db1c4` | **BLOCKING** — cleanup and replay-integrity defects |

**P2 — VERIFIED evidence**

CPU tests: **155 fork, 184 router, 272 targeted stack tests passed**. Registry goldens ran with `MLX_REQUIRE_STACK_REGISTRY=1`; all 11 real entries validated. Independent checks against actual `main` code confirmed first-pick command equality and six default serializer byte comparisons.

No repository edits, pushes, servers, real model loads, GPU computation, or port-8000 requests. Prior review files remained unread.

**P3 — Closure table**

Grouped by the supplied finding descriptions, without reconstructing unavailable reviewer-ID mappings.

| Claimed closure | Assessment and evidence |
|---|---|
| Loaded MTP drafter checked after resolution | **Closed** — initialization guard; `TestB6LoadedMtpDrafter` |
| Self-test shape/dtype/non-finite rejection; finite straddle difference | **Closed** — `_invalid`, `_bits_differ`; `TestB7SelfTestValidity` |
| AB serves joint; deferred counters; exception cleanup preserves error | **Closed** — `attend/end_block/discard_pending`; AC7/B8 tests |
| Device discovery fails closed; cached suffix agreement | **Closed** — device checks; B9 tests |
| Real mirror and STEP-1 positions, including 1024/1025 | **Closed** — B10 tests exercise real plan against independent 44-cell table |
| Default path avoids new-module import | **Closed** — guarded imports; D6 import-hook tests |
| GPU-only self-test, watchdog including probe, local RNG, cached device | **Closed in code/CPU tests** — load ordering and D7/round-two tests |
| AC8 unmodified drafter and final state | **Partial** — state comparison exists; positive genuine-draft acceptance remains unproved: **D5** |
| Native KV determined by `kv_bits`; real registry loads | **Closed locally** — fork/router goldens; CI enforcement remains **D6** |
| Request-scoped counters; streaming session-cache; default bytes | **Closed** — AC9 endpoint tests plus independent main serializer comparison; `_step` limitation documented |
| v8/v7 compatibility, scan closed set, override refusal | **Closed** — provenance tests; multi-model cleanup ordering remains **D2** |
| AB overlay observation, post-load checks, non-pooling | **Closed** — provenance tests and `compare_predictor` refusal |
| Empty/duplicate/unequal expected sets; exact coverage; complete journals; exit codes | **Closed for tested valid structures** — AC11 tests; malformed-journal gaps remain **D3** |
| Resume hashes, drift refusal, serving identity/config SHA; clean aborted resume | **Partial** — tests pass, but serving-code identity is omitted: **D1** |
| Digest recomputation, mandatory identity/draft members, uniform row state, joint coverage | **Partial** — ordinary cases pass; **D1/D3** bypasses remain |
| Auth on preload and requests | **Closed** — client and replay auth tests |
| Failure finalization/C106/original error | **Partial** — ordinary exceptions covered; interruption escapes: **D4** |
| Autouse provenance pin removed | **Closed** — opt-in `pin_mtp_scan`; unpinned refusal tested |
| Scope/markers | **Verified** — localized production hunks, M58 markers, protected verifier paths unchanged; diff checks clean |

**P4 — New findings**

Paths below are relative to the named repository. All six are **VERIFIED**, with runtime failures reproduced using CPU/in-memory checks.

- **D1 — HIGH, stack:** `benchmark/bench/parity_replay.py:135`, `:272`, `:475`. Resume never compares retained journal `code` with current serving code, then replaces it. Reproduction retained an old-code row, added a new-code row, and returned **0**, stamping both as new. Compare also returns **0** when one side lacks `code`. **Minimal fix:** require complete serving-code hashes, validate before resume, preserve attribution, and refuse missing identity in modern comparisons.

- **D2 — HIGH, stack:** `benchmark/bench/generate.py:319`, `:342`. Validation and deletion are interleaved by model. With `[valid, unresolved]`, `--clean-stale` deletes the first model’s rows before refusing the second. Reproduction observed one deletion before refusal. **Minimal fix:** validate every selected model and compute the entire cleanup plan before any deletion.

- **D3 — MEDIUM, stack:** `benchmark/bench/parity_replay.py:390`, `:449`. Non-string content/reasoning skips digest recomputation. Two differing content objects with matching stale digests returned **0**. A complete journal carrying `served_config_drift` also returned **0**. **Minimal fix:** reject invalid field types and drift stamps before comparing; return integrity exit **2**, including malformed structural inputs.

- **D4 — MEDIUM, stack:** `benchmark/bench/parity_replay.py:338`. `except Exception` excludes `KeyboardInterrupt`. Injecting interruption during replay produced **zero C106 calls**, leaving the existing journal unfinalized. **Minimal fix:** finalize interruption paths while preserving/re-raising the original exception.

- **D5 — MEDIUM, fork:** `mlx_vlm/tests/test_mtp_verify_scan_generation.py:233`, `:248`. The unmodified-drafter test never requires positive acceptance. The added “real acceptance” test substitutes oracle proposals on alternating rounds. Deterministic reproduction: **39 unmodified rounds accepted zero drafts; mixed genuine rounds all zero, oracle rounds all three**. **Minimal fix:** construct a deterministic fixture yielding accepted genuine proposals and rejection/rollback; assert those events explicitly while comparing final states.

- **D6 — MEDIUM, fork/router:** fork `mlx_vlm/tests/test_mtp_verify_scan.py:1523`; router `tests/test_config.py:508`; workflows `tests.yml:44` / `ci.yml:37`. Missing sibling registry still permits a green CI run with skipped goldens: workflows neither supply the registry nor require it. **Minimal fix:** provision a pinned real registry and set `MLX_REQUIRE_STACK_REGISTRY=1` in CI. Explicit invalid environment paths already fail correctly.

**ASSUMPTION / unverified:** GPU bit identity, live readiness behavior, and performance qualification. CPU evidence does not establish those. No additional production routing defect was found within the qualified domain.

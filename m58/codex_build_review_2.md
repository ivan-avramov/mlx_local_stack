**P6 — Verdicts at unchanged HEADs**

| Repo | HEAD | Verdict |
|---|---|---|
| Fork | `42fd4816` | **FIX-THEN-SHIP** |
| Router | `8aa6a75` | **FIX-THEN-SHIP** — CI golden-test gap; command/config behavior verified |
| Stack worktree | `c7d588f` | **BLOCKING** — replay integrity and unresolved-provenance escapes |

**P7 — Round-1 closure**

“Closed” below means code and test coverage inspected; execution limits follow.

| Finding | Closure | Evidence |
|---|---|---|
| Resolved, loaded MTP drafter guard | Closed | Guard follows resolution/compatibility handling; `TestB6LoadedMtpDrafter` exercises both failures. |
| Self-test invalid outputs versus finite representation difference | Closed | `_invalid()` precedes `_bits_differ()`; `TestB7SelfTestValidity`. |
| AB deferred counters; exception cleanup preserves original error | Closed | `end_block()` advances AB counters; verifier discards pending comparisons then bare-raises; `TestB8ABFinalization`. |
| Device discovery and cached/live suffix agreement | Closed | Fail-closed checks; `TestB9DeviceDiscoveryConsistency`. |
| Real mirror threshold coverage | Mostly closed | Independent execution matched all **44 cells / 208 swept**, including positions and **64@1024 / 128@1025**. Committed position test remains weak: D8. |
| AC8 unmodified drafter and final state | Closed in source | Real proposals; compares seed, position, acceptance history and cache arrays. Fork execution unavailable. |
| KV refusal based only on `kv_bits`; both router policies restored | Closed | Native-cache predicate and real-registry golden coverage. |
| Real registry / real command golden | Closed locally; CI gap | **11 entries validate**; actual HEAD/main first-pick command builders match. D5. |
| `_step` counter limitation documented | Closed | Code and worktree spec explicitly disclose it. |
| Compare nonempty/unique/equal expected sets, exact coverage, positive pairs, complete journals | Closed | Checks present; broader integrity and legacy-exit defects remain: D2. |
| Empty run selection; resume payload+seed hash | Narrowly closed | Both checks present; resume can still rehabilitate contaminated rows: D1. |
| Closed-set validation everywhere; unknown refusal before cleanup | **Not closed** | D2/D3. |
| Auth including preload | Closed | Shared GET/POST headers and replay POST; auth tests passed. |
| C106 failure finalisation / original error | Partial | Transport/preload failures preserve errors; other exits escape or omit drift stamp: D4. |
| Autouse scan pin removed | Closed | `pin_mtp_scan` is opt-in. |
| AB overlay observation, post-load re-resolution, non-pooling | Mostly closed | Resolver, ladders and compatibility checks covered; `generate` uses manual comparison rather than `expect=entry` and permits unresolved states: D3. |
| Null worker refusal; predictor rejects AB arms | Closed in source | Explicit guards and targeted tests present. |

**P8 — Findings**  
Paths are relative to the named repo. All findings are **VERIFIED** by source inspection; reproduced cases are identified.

- **D1 — HIGH, stack: `benchmark/bench/parity_replay.py:176`.** Resume validates request hashes but not prior drift, config hash or row serving mode. **Reproduced:** an aborted, drift-stamped AB journal resumed under `per_query`, made zero requests, returned 0, became `complete`, and lost its drift stamp. **Fix:** reject contaminated journals; validate retained rows against the frozen serving identity before calculating `done`; preserve provenance history.

- **D2 — HIGH, stack: `benchmark/bench/parity_replay.py:291`.** Mandatory fields are checked only for presence; recorded content hashes are trusted, and row runtime is unaudited. **Reproduced:** null hashes/`draft`, invalid scan values, and changed content with a stale digest all compare successfully. Actual pre-M58 rows also return **2 while printing “exit 3”**, because modern mandatory fields are audited before legacy handling. **Fix:** separate legacy/modern schemas; validate non-null identities and draft members, recompute content hashes, and validate modern row provenance.

- **D3 — HIGH, stack: `benchmark/bench/generate.py:459`; `benchmark/bench/provenance.py:1628`.** `generate` lacks the unresolved-state guard before cleanup. `_runtime_block()` accepts overriding a resolved scan; `build_manifest()` accepts missing/`unknown` scans. **Reproduced:** a missing registry model under the default profile produced `unknown`, and `clean_stale` attempted to delete both result and manifest. **Fix:** resolve all models with `assert_serving_state()` before cleanup; use `expect=entry` after load; reject unknown/missing values and overrides of observed serving controls.

- **D4 — MEDIUM, stack: `benchmark/bench/parity_replay.py:85`, `:264`.** Malformed structures can bypass finalisation: `usage=[1]` raises `AttributeError` outside the protected request call. Separately, final C106 refusal calls `_abort(check_exit=False)` without supplying a drift stamp. Both reproduced. **Fix:** type-check response structures and wrap post-entry processing in one failure-finalisation path that retains the original error and recorded drift.

- **D5 — MEDIUM, fork/router: `mlx_vlm/tests/test_mtp_verify_scan.py:1506`; `tests/test_config.py:526`.** Missing or misconfigured registry paths make the golden tests **skip**, allowing green CI without the compatibility protection. **Fix:** provision the real registry in required CI and fail when its configured path is absent.

- **D6 — MEDIUM, fork: `mlx_vlm/server/generation.py:211`, `:1540`.** Default loading imports and executes the new module through `resolve_policy()` and `require_loaded_mtp_drafter()`. Thus “default never touches the module at runtime” is false, although serializer preservation passed. **Fix:** short-circuit default/no-AB before import and guard the post-resolution call.

- **D7 — MEDIUM, fork: `mlx_vlm/mtp_verify_scan.py:493`, `:528`.** The 30-second bound is checked only after completion; the preceding dtype probe is outside that timer. A hung call never reaches the check. The router readiness timeout marks failure but does not terminate the worker (`src/mlx_serve/process_manager.py:346`). **Fix:** enforce a worker-level deadline covering the probe and both cells, with guaranteed termination on expiry.

- **D8 — LOW, fork: `mlx_vlm/tests/test_mtp_verify_scan.py:1416`.** The leading-position test checks only its own constant list; it never invokes the mirror or derives `qL−d`. **Fix:** compare each query-prefix plan against the joint plan and assert the resulting positions against the table. My independent execution did this and passed.

**P9 — Verification and limits**

- **Executed:** 23 router tests; 33 stack tests in read-only subsets; 18 HEAD-versus-main timing serializer comparisons; real registry/command comparison; independent threshold check; in-memory failure reproducers.
- **Inspected:** joint output serving, shared QKV, deferred AB evaluation/cleanup, GPU refusal before readiness, per-request counters and streaming cached-session plumbing.
- **Unavailable:** full suites—temporary-file writes are forbidden; fork collection additionally aborts in MLX/nanobind. GPU identity, timing and live startup remain **ASSUMPTIONS pending qualification**, not verified results.
- Scope/markers passed: no unexpected fork files, seven protected files unchanged, all shared-file M58 hunks marked. Reviewed trees remained clean. No writes, pushes, servers, model loads or port-8000 requests performed. Historical no-push/test-first claims cannot be proven from local HEADs alone.

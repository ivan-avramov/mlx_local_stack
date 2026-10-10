# M58 build: cold review, round 2 (Claude)

Heads reviewed: fork `../mlx-vlm` `m58-joint-verify` @ `42fd4816`, router `../mlx-serve` `m58-joint-verify` @ `8aa6a75`, stack worktree `.claude/worktrees/m58` `m58-provenance` @ `c7d588f` (`git diff main...HEAD`). I did not read the prior review files.

**Note:** while this review ran, the stack worktree picked up UNCOMMITTED edits (from 21:15 local): 18 files, including `generate.py`, `parity_replay.py` and `provenance.py`, with "D3" markers. This review judges committed HEAD only. All stack tests ran on a clean `git archive HEAD` export under `$TMPDIR`.

## Evidence run (CPU only; no server, no model, no port 8000)
- Fork: `test_mtp_verify_scan.py` + `test_mtp_verify_scan_generation.py`: 132 passed.
- Router: `tests`: 183 passed.
- Stack HEAD export, M58 and M50/M57 provenance files: 186 passed. The full `bench/tests` suite gave 2909 passed, 3 skipped, but it ran in the live worktree, which started changing partway through.
- VERIFIED, independent check: main's and the branch's router `config.py`/`process_manager.py`, run against the real `main_models.yaml`, build identical worker commands for all 11 registry entries.
- VERIFIED, independent check: main's and the branch's `GenerationTimings` / `StreamingTimings` produce identical `model_dump_json()` bytes under the default (with and without M57 sdpa/draft fields).
- Mutation runs on `$TMPDIR` exports (repos untouched):
  - Fork: 30 mutants, 23 killed. Survivors are listed in D5.
  - Stack: 18 mutants, 18 killed. These covered the compare gates, resume hash, AB observation on worker and registry, intro version, predictor AB refusal, loaded re-checks, unknown refusal, auth, closed set and draft identity.

## Verdicts
| Repo | Verdict | Reason |
|---|---|---|
| fork | **SHIP** | Served numerics are confined to rules 1–7. Findings are guard/test quality (D4–D8). |
| router | **SHIP** | Minimal and verified. Golden-test caveat D4. |
| stack | **FIX-THEN-SHIP** | G1b tooling can report "identical, exit 0" without proving the joint path ran (D1), and a resumed journal can mix policies (D2). |

## Round-1 closure table
| Item | Status | Evidence |
|---|---|---|
| Loaded-MTP-drafter guard after resolution | CLOSED | `generation.py`: `require_loaded_mtp_drafter` runs after `load_drafter`/compat fallback. B6 tests. Mutant N4 killed. |
| Self-test: shape/dtype/non-finite always reject; straddle needs a finite representation difference | CLOSED | `mtp_verify_scan.py:487-502` (`_invalid` before `_bits_differ`). B7 tests. M13 killed. Gap: D5 (M12). |
| AB counters only in `end_block()`; `discard_pending` on exception re-raises the original | CLOSED | `mtp_verify_scan.py:309-333`; `speculative_verifier.py` try/except. B8 tests. M9, N11 killed. |
| Device discovery fails closed; cached mirror suffix == live | CLOSED | `mtp_verify_scan.py:85-105`. B9 tests. M3 killed. Gap: D5 (N3). |
| Threshold tests on the REAL plan, only `device_info` mocked, STEP 1 table | CLOSED | `test_mtp_verify_scan.py:1342-1437`: 44 cells, keys 1024–1028/8193–8196/32769–32772/65537–65540, length-2 at 1024/1025, 64@1024 / 128@1025. One tautological test (D5). |
| AC8 with an unmodified drafter, comparing drafter final state | CLOSED, weak | `test_b11`. VERIFIED: the random drafter accepts 0 tokens in all 39 rounds (D5). |
| Quantized-KV refusal on `kv_bits` only; golden tests on the real registry | CLOSED | `require_environment` (`if kv_bits:`). Fork and router golden tests pass here. Silent-skip caveat: D4. |
| `_step` batching path documented as reporting no counters | CLOSED | `generation.py` note + spec F5 line. |
| Router: `kv_quant_scheme` rule reverted for both policies | CLOSED | `git diff main...` shows no scheme rule; `test_native_kv_is_decided_by_kv_bits_only…`. |
| Router golden: every entry validates; first-pick command byte-identical to main | CLOSED | Tests, plus my all-11-entries main-vs-branch comparison. |
| `parity_replay compare` integrity rules; exit codes 1/2/3 | CLOSED | `parity_replay.py:274-371`. S1–S5, S18 killed. Gating gap: D1. |
| `run` refuses an empty selection | CLOSED | `:150`. |
| Resume validates rows against the frozen payload+seed hash | CLOSED | `:176-180`. S12 killed. Remaining mixing gap: D2. |
| Closed-set `mtp_verify_scan` on every path | CLOSED | Resolver, `assert_serving_state`, `_runtime_block`, `build_manifest`, generate precheck (ServingStateError ⊂ ServedConfigError → re-raised before cleanup), parity entry and per row. S14, S16 killed. Residual: D3. |
| Auth on every request incl. preload | CLOSED | `client._post`/`_get`, `parity_replay._post`; b4 test. S15 killed. |
| C106 on failure: drift stamp, original error kept | MOSTLY | `_abort` paths stamp `served_config_drift`. The end-of-run C106 failure path does not (D3b). |
| Autouse conftest pin removed (opt-in `pin_mtp_scan`) | CLOSED | `conftest.py` fixture is not autouse. |
| AB gate rows never pool; re-resolve after load with `expect` | CLOSED | `+ab` value distinct in fingerprint and `is_compatible`; `expect=` in capacity, retrieval, reasoning and parity; own check in generate. S6, S7, S10, S11 killed. |
| Null worker cmdline refused | CLOSED | `parity_replay.py:226`. S13 killed. |
| `compare_predictor` rejects `joint_v1+ab` | CLOSED | `compare_predictor.py:198`. S9 killed. |

## Challenge areas (summary)
1. **Joint path outside rules 1–7 / default-path runtime touch:** none found (VERIFIED by reading and mutants).
   - Under `per_query` the only runtime cost is a missed `getattr` per layer and a try/except in `__call__`.
   - The module is imported at load only, and `require_loaded_mtp_drafter(None, …)` is a no-op.
   - Prefill never enters the verifier. `qwen4_exp` inherits the hook, but it is never stamped (exact-type match and `model_type` check).
   - The domain checks query dtype/head-dim only (D6).
2. **Straddle predicate:** VERIFIED.
   - It calls the same `language._qwen3_5_sdpa_vector_plan(seq, n_q, n_kv)` as the ragged-kernel mirror, per call, with the live suffix cross-checked.
   - For `s` the plan is monotone in N, so comparing the endpoints `prefix+1` and `key_length` is sufficient.
   - ASSUMPTION (MLX source not in repo): MLX computes `n_simds = gqa·qL` for the joint call. The mirror is fed `gqa`. These are equivalent only while gqa > 4 on `s` (domain gqa = 6). Widening the domain to gqa ≤ 4 would break it, but it fails closed: the load self-test's 2048-key identity cell would refuse.
3. **AB:** VERIFIED.
   - The joint output is served (M5 killed); one `mx.eval` per round (plus `counters()`); pending entries are dropped on exception and on an `end_block` raise (the swap happens first).
   - Lifetime `verify_blocks_*` advance in `attend()` even for an aborted round, so after an exception lifetime `ab_blocks < joint_v1`. Per-request deltas are unaffected. Harmless.
4. **Self-test:** GPU-only (`force_calls` defaults to `_gpu_enabled`), raises before READY (AC6 test), budget checked after the fact. It consumes the global RNG (D7).
5. **Counters:**
   - Per-request reset, presence only under a policy, and the streaming session-cache path are VERIFIED (tests and mutants N7, N8).
   - Default bytes VERIFIED by serializer comparison against `main`. The test itself only checks that `verify_*` keys are absent.
6. **Golden tests:** both load the real `main_models.yaml`.
   - Router: the real `_load` and real `_build_command`.
   - Fork: the real registry plus the real `_apply_mtp_verify_from_env` on a tiny LM, with the self-test and domain stubbed.
   - Both SKIP silently when the path is wrong (D4).
7. **Provenance v8:**
   - v7 compat, `--clean-stale` v7 safety and AB non-pooling are tested and mutant-checked.
   - "unknown" is reachable only via model-not-in-registry, an unreadable registry, or no-model-given. In the runners it is refused by `assert_serving_state` and M50, and generate's `params_for` fails first.
8. **parity_replay:** G1b can pass on nothing (D1); resume mixing (D2); drift stamp gap (D3b).
9. **Test quality:** D5.
10. **AGENTS.md:**
    - VERIFIED: `# Fork (M58)` markers on every added hunk (AC5 test plus reading); scope limited to the listed files; no PII or absolute paths in the three diffs; no `m58*` remote refs and no upstream tracking (nothing pushed); submodules not bumped.

## Findings

**D1 (Medium, stack): `parity_replay compare` can certify G1b without the joint path having run.**
- Where: `benchmark/bench/parity_replay.py:309-371`; `joint_rows` is printed (`:346`) but never gated.
- Scenario: the joint arm is launched with the default overlay, or both arms run `per_query`. Compare prints `identical=20`, `joint_rows A=0 B=0` and exits 0.
  - A cross-version replay (different fork SHA, model or attention policy) also compares as long as the keys and hashes match.
  - A `joint_v1+ab` side is accepted as a G1b arm.
- Minimal fix: derive each side's served state from its rows' `runtime` (`mtp_verify_scan`, `draft_kind`, `attention_policy`, `lazy_prompt_embeddings`) and `worker`.
  - Integrity-fail (exit 2) when a side's rows are not uniform, or when a side is `joint_v1+ab`.
  - Report `scan A/B`. When the scans differ, exit 2 unless the joint side has `verify_blocks_joint_v1 > 0` on ≥ 18/20 rows (G1b rule); when they are equal, label the comparison as a reload control.
  - Add tests for per_query vs per_query labelled as joint, and for mixed-scan rows.
- Status: VERIFIED by reading. Mutants confirm the current checks but cannot cover the missing one.

**D2 (Medium-Low, stack): resume can mix serving states in one journal.**
- Where: `parity_replay.py:168-187`. Resume compares only `router["config"]` (path) and per-row payload hashes.
- Scenario:
  - The operator edits the same overlay file between loads (`mtp_verify_scan` flipped), then resumes the same `--out`. The rows are kept: their `runtime.mtp_verify_scan` differs from the entry state, but nothing compares them.
  - Combined with D1, compare treats the side as one policy.
  - A journal stamped `served_config_drift` (aborted) also resumes.
- Minimal fix: on resume, refuse when `router.config_sha256` differs from any journal router block, when a row's `runtime.mtp_verify_scan` (and `draft_kind`/attention controls) differs from `entry_state`, or when the doc carries `served_config_drift`.
- Note on the in-flight edit: the uncommitted change appears to implement this, but it also refuses `status != "running"`. That blocks resuming an `aborted` journal (e.g. after a transport abort), which is the main resume case. Confirm that is intended.
- Status: VERIFIED by reading.

**D3 (Low, stack): provenance residuals.**
- (a) `provenance.py:1628`: `_runtime_block` applies the caller's `runtime` dict AFTER the observed controls, so a caller could override `mtp_verify_scan` / `attention_policy`. `build_manifest` (`:1656`) checks the closed set only when the key is present, and lets "unknown" through. No current caller passes those keys (`run_agentbench_os`, `vision_gate` pass client knobs), so the risk is latent. Fix: refuse a caller key that collides with an observed control, and require a resolved scan in `build_manifest`. The in-flight edit does this.
- (b) `parity_replay.py:264`: when the end-of-run C106 check fails, `_abort(..., check_exit=False)` records only `error`, with no `served_config_drift` stamp (AGENTS.md: drift stamps `served_config_drift`). Fix: build `served_config_drift_record(router, BASE, e)` in that branch. The test `test_run_c106_exit_drift_aborts_nonzero` checks only `status`.
- Status: VERIFIED by reading.

**D4 (Low-Medium, fork + router): golden tests skip silently in the qualification and CI layouts, and the router golden is a brittle snapshot.**
- Where: fork `mlx_vlm/tests/test_mtp_verify_scan.py:1500-1506`; router `tests/test_config.py:505-526`.
- Scenario:
  - The registry is looked up at `<repo>/../mlx_local_stack/main_models.yaml`. As submodules (`mlx_local_stack/src/mlx-vlm`, which is how the spec runs qualification), that resolves to `src/mlx_local_stack/main_models.yaml`, so the tests skip with only a reason string.
  - VERIFIED: my `$TMPDIR` fork export ran with "1 skipped" = the golden test.
  - Separately, `_FIRST_PICK_MAIN_COMMAND` hardcodes `generation_defaults`. Any certified sampling change in the registry turns the router suite red, and nothing points at the cause.
- Minimal fix:
  - Also try `parents[3]/main_models.yaml` (submodule layout).
  - Make a missing registry a FAILURE unless `MLX_STACK_REGISTRY=skip` is set explicitly.
  - Router: compare against `main`'s `_build_command` output computed at test time (e.g. `git show main:` modules, as I did), or snapshot only the non-sampling flags.

**D5 (Low, fork): test gaps.**
- Surviving mutants:
  - M12: deleting "straddle cell is not a known positive on this device" (`mtp_verify_scan.py:525`).
  - N2 / N3: removing the head-dim check or the `device_classes` check. The mirror check compares only the last character, so `applegpu_g18s` would pass.
  - N5: removing `require_gpu()` (the self-test still refuses).
  - N9: removing the 30 s budget check.
  - N12: len1 blocks leaking into `verify_fallback_reasons`. G1a's empty-histogram criterion depends on that not happening.
  - M8: the hook overriding a non-None `output` from the left-padded helper.
- Tautology: `test_b10_mismatch_positions_are_the_first_qL_minus_d` (`:1416`) asserts on its own table.
- AC8 `test_b11` (`test_mtp_verify_scan_generation.py:207-217`): VERIFIED 0 accepted in all 39 rounds, so drafter-state identity is never exercised on an accepting round with real proposals.
- Fix: one test per survivor, and assert `any(a > 0)` in b11 (seed or bias the micro-drafter until it accepts).

**D6 (Low, fork): the domain check reads only the query's dtype and head dim.**
- Where: `mtp_verify_scan.py:250-258`.
- Scenario: a qwen3_5 entry whose cache dtype differs from the query dtype (e.g. fp16 cache with bf16 queries), or whose V head dim differs, would take the joint path outside STEP 1's measured domain. The load self-test builds q/k/v in one dtype and shape, so it would not catch this.
- Minimal fix: add `keys.dtype == values.dtype == queries.dtype` and `values.shape[-1] == keys.shape[-1] == domain.head_dim` to the domain clause.
- Status: VERIFIED by reading. No such entry exists today.

**D7 (Low, fork): the self-test draws from the global MLX RNG.**
- Where: `mtp_verify_scan.py:481-483`.
- Effect: under `joint_v1` the process RNG state at the first request differs from `per_query`. G1b is safe only because every frozen payload carries an explicit seed; any unseeded request differs between arms by construction. Self-test failures are also not reproducible.
- Minimal fix: use a fixed local key, e.g. `k0 = mx.random.key(0)`; `mx.random.normal(shape, key=...)`.
- Status: VERIFIED by reading; impact ASSUMPTION.

**D8 (Low, fork, performance): `mx.device_info()` is queried twice per `classify`, i.e. per full-attention layer per round.**
- Where: `mtp_verify_scan.py:255-256`.
- Effect: about 32 dict-building C++ calls per verify round on the hot path. At 8K, where the joint gain is predicted at ±2 %, this is a confound. ASSUMPTION: the cost is µs-scale; not measured (no GPU allowed).
- Minimal fix: resolve the device class and the mirror-suffix agreement ONCE when the policy is constructed (load time, which is also when the self-test proves the mirror), store them, and reuse them in `classify`. The device cannot change in-process.

## Not findings (checked)
- Length-2 under `joint_v1`: "causal" string non-straddle / per-query straddle, per the C120 ruling.
- Under `per_query`, the shipped length-2 bool-mask branch is byte-identical (AC1 test).
- An incoming 4-D bool mask path pays one `.item()` sync per layer (`_rows_are_contiguous_runs`). It is rare (the verifier passes "causal"), and its docstring "synchronises once" understates the cost.
- Router `mtp_verify_ab` is accepted from overlays only alongside `joint_v1` (bool-typed). The stack treats a registry `mtp_verify_ab: true` as `joint_v1+ab`, which deliberately deviates from the spec's "never from the registry" wording and matches the round-1 ruling.

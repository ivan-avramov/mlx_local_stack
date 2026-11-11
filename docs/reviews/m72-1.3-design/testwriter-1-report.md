# Test-writer report, delivery 1 — M72 1.3 TQ4 production mode (spec v1.1 + "Modes (C319)")

Raw baseline outputs (verbatim pytest `-rA`): `../scratch/baseline_fork.txt`, `baseline_serve.txt`, `baseline_stack.txt`.
Baseline = the three copies at the parent commit, nothing of the change present. Metal available, device `applegpu_g17s`, MLX 0.32.4.
Nothing was committed; only the files named in the brief plus `../scratch/` were created.

## Files

| codebase | file |
|---|---|
| fork | `mlx_vlm/tests/test_tq4_m72_support.py` (helpers + 5 instrument tests), `..._kernels.py`, `..._mode.py`, `..._routing.py`, `..._memory.py`, `..._generation.py` |
| mlx-serve | `tests/test_tq4_m72_config.py` |
| stack | `benchmark/bench/tests/test_m72_13_provenance.py`, `test_m72_13_harness.py` |

No marker added (the fork defines no `slow`; long-context rows are unmarked). Classes: N = new behaviour, I = invariant, F = reproduces a failure the spec fixes, T = instrument check (holds on today's code).

## Tests

### `test_tq4_m72_support.py` (instruments, all T/I, all pass on baseline)
reference vs today's decode block; reference vs today's prefill; A1 judge rejects planted leak/drop; synthetic model has the supported shape and the served cache mix (TQ4 layer + native last full-attention layer); greedy decode deterministic in-process.

### `test_tq4_m72_kernels.py` — A1 on `tq4_fast`, R2, R4, scope predicate, counters, copy-free
- `dequant_rotated`: capacity-sized fp16, bit-identical to the generic form, T in {1,511,2049,40000} (N, A1/p2s); bf16 option + refusal of other dtype (N); T outside [1, offset] refused (N).
- p2s prefill A1: prototype sweep 10 (T,L) pairs ≤ 40,960 (N); T ∈ {65537,131072,260096} × L ∈ {512,37}, heads 0/6/12/18 (N); T below `cache.offset` (N); largest chunk finite (F); planted-key negative controls T+1/T−1 fail A1, true call passes (N); garbage beyond T ignored (N); inputs unmodified + deterministic (I).
- mma verify A1: prototype sweep 10 T × k∈{2,3,5} (N); target context 3 T × 3 k (N); block/tier edges incl. 65,535…65,538 and 512-multiples (N); fully-masked blocks finite, R2 (N); kernel reads passed lengths not `cache.offset`, planted bait + leak/drop controls through the public interface, k=2,3,5 (N, threat); garbage beyond last length ignored (N); out-of-contract arguments refused (N); output contract/determinism (I).
- D2 decode: bit-identical to the singleton at T ∈ {2049,4097,8193,40000,65537,131072,260096} (N,F); on a state sliced below the offset at the 8,192/32,768/65,536 tiers (N,F); T ≤ 2048 entry point bit-identical (N); reads T not the offset (N, threat).
- D2 multi-query (`exact=True`): per-query bit-identity k=2..5 × T∈{2053,4097,8193,40000,65537,131072} (N); k=2,5 at 260,096 (N); tier straddles incl. [65535..65538], [65534..65538], [8191..8194], [32767..32771] (N); below offset (N); finite on block edges (N); exact vs fast agree within tolerance (N).
- copy-free: instrument — today's decode copies the strided state (T, passes baseline); D2 decode and both verify kernels peak < 0.5 × used K/V bytes at 260,096 (F).
- `supports`: in scope (None/"causal", L ∈ {1,2,37,512}); array mask, sinks, n_q 16, D 128, batch 2, fp16, fp32, legacy flag (attr and ctor), block override, bits 3, mixed widths, prod codec, subclass, 2 KV heads, native cache, empty cache, `None` all `(False, non-empty reason)` without raising; batch class → reason `batch_cache` (N).
- `route_counts` monotone str→int; `self_test()` returns a non-empty dict; kernels refuse a batch cache (N).

### `test_tq4_m72_mode.py` — interfaces, A3 refusals, A7, CLI/env, load order
- `MODES`, `resolve_mode` (None→None, values, 7 invalid spellings refuse) (N).
- `require_environment`: valid for both modes × kv_bits 4/4.0; each of kv_bits {0,None,8,3}, scheme {uniform,None}, policy {auto,None}, scan {per_query,None} alone refuses, both modes; `TQ_DECODE_2PASS_LEGACY` ∈ {1,true,TRUE,yes} refuses, {0,false,no,""} accepts; unknown mode refuses (N).
- A3 invariants (pass on baseline): `mtp_verify_scan.require_environment` refuses kv_bits {4,4.0,8,2.5}; native + draft-kind rules unchanged; `JointV1Policy.classify` sends TQ to `per_query/"cache"`.
- A7: passes + returns dict; q_norm bound at γ 1000/1024 pass, 1025/4096 refuse; error names layer; codebook bound (key/value codec × 1.0/1.5) (N).
- `apply_to_model` count == attention modules, refuses unsupported family and unknown mode; `self_test_model` returns dict, both modes (N).
- CLI: `--tq4-attention` → `MLX_VLM_TQ4_ATTENTION`, not stale on next start; unknown value rejected after the valid value is shown accepted (N).
- Load order through `ResponseGenerator._initialize_model` with recording stages: exact order (8 stages) × 2 modes; a failure at require_environment / check_fp16_range / apply_to_model / self_test_model propagates and nothing later runs; require_environment failure precedes every other stage; mode absent runs no mode stage; real `mtp_verify_scan.require_environment` accepts kv_bits 4 when the mode resolved (both modes) and still refuses it without the mode (A3); incompatible companions (attention policy auto, scan per_query, legacy env) and kv_bits {0,8,None} refuse before check/apply (N, F).

### `test_tq4_m72_routing.py` — A2, one test per table row, through the model (counter + "no other route counter moved" + output standard)
prefill chunk `p2s` (×2 modes), first chunks ≤2048 are `p2s`; short row `mma_prefill` L=2..5; L=6 `p2s`, L=1 `d2`; short-row boundary T_eff 2048/2049; verify block of 3 is `mma`, not `mma_prefill`; plain decode `d2` (>2048) / `single_pass` (≤2048) bit-identical; decode boundary 2048/2049; width-1 verify; v1 verify k=2..5 `mma` (near), v1 below 2048 `mma`; k=6,7 `per_query:k_gt_5` + `d2`, bit-identical; exact k=2..5 `d2_verify` bit-identical, no `mma`; exact short `per_query:short` and boundary lengths[0] 2048/2049; native layer `native:{prefill,verify,decode}`, prefill `force_fused=True`, verify one joint call with `mask="causal"`, decode one query; legacy flag and block override fall back (`fallback:*`, no fast route, bit-identical) for decode/verify3/prefill512 × 2 modes; fp32 queries fall back; `/health` details carry the counters; mode absent: no counter moves and `tq4_fast`/`tq4_attention` never imported on the request path (tq4, native); native16 with shipped policies runs (I, passes).

### `test_tq4_m72_memory.py` — per-layer evaluation (behavioural)
instrument: a lazy chain of 9 prototype scratch calls holds ≥3 scratches, per-layer-evaluated ≤2 (T, passes); through the model (20 layers, 9 TQ4, capacity 65,536): one prefill chunk peaks ≤2 scratches and `p2s` ≥ 9 (both modes, T_eff ≤2048 and >2048) (F); the scratch is capacity-sized (peak ≥0.9 scratch at T_eff 1,024) (N); buffer cache after 4 chunks ≤3 scratches (N); active memory returns to the resident set (N).

### `test_tq4_m72_generation.py` — A3, A4
A3 goldens (digests recorded on the parent commit, suite numerics `MLX_ENABLE_TF32=0`, two separate processes agreed; skip with reason on another arch/MLX): TQ4 T=600, TQ4 T=2300, native T=2300, TQ4 MTP ON (scripted full-acceptance drafter) (I, pass on baseline); scenarios deterministic (I). A4(a) 64 greedy tokens from T=2030 mode off vs on, tokens + logits bitwise, `single_pass` and `d2` both fire (×2 modes). A4(b) prefill last logits mode on vs off at T=2600/4000, near + same argmax (×2). A4(c) `m72_exact` MTP ON == OFF, n=256, greedy/seeded × accepting/rejecting drafter × block 3/5/7, `d2_verify`>0 and `mma`=0 for k≤6, `per_query:k_gt_5` for 7; `m72_v1` MTP runs through `mma` (not asserted exact).

### `tests/test_tq4_m72_config.py` (mlx-serve)
absent default falsy; both values load from the registry (full companions); 8 unknown values refuse; each companion wrong refuses (12 cases × 2 modes: kv_bits 0/8/2, scheme ""/uniform, policy ""/auto, scan ""/per_query, draft_kind ""/suffix, type text); full combination accepted; message names the key; `fused_v1`/`joint_v1` + kv_bits 4 refused without the mode (I, pass on baseline); refused with other kv_bits even with the mode; valid with kv_bits 4 + mode (F); native shipped combination stays valid (I); mode on a native cache refused; other rules still apply; command byte-identical without the key (`{}` passes on baseline, `""` kwarg fails); `--tq4-attention <mode>` once, companions travel, pair removal equals the bare command; flag never emitted for text/absent (I, pass).

### stack
`test_m72_13_provenance.py`: fingerprint version ≥ 9 and control `tq4_attention` registered with a non-mode default; earlier controls unchanged (I, pass); registry value read (source registry), absent = default; worker flag observed (source worker); worker without flag = default; disagreement refuses (C35) ×3; unrecognised value refuses; `assert_serving_state` carries it; runtime override refused; manifest records it; pre-bump rows read the default and pool only with the default; modes never pool; unresolved never pools; v7/v8 rows stay compatible (I, pass).
`test_m72_13_harness.py`: existing variants still parse (I, pass); `tq4_m72` variant; `--capacity` default = tokens, independent when given; driver passes variant/capacity to every leg; default capacity; variant:eval spec unchanged (I, pass); registry pick unchanged (kv_bits 0, no `tq4_attention` anywhere) and keeps fused_v1/joint_v1/mtp (I, pass); docs `serving-path.md` and `box-notes.md` carry `tq4_attention`, `m72_v1`, `m72_exact`.

## Baseline outcomes (verbatim summary lines)

- fork (6 files, 363 tests): `105 failed, 19 passed, 2 warnings, 239 errors in 10.71s`
- mlx-serve (`tests/test_tq4_m72_config.py`): `52 failed, 5 passed in 0.25s`. Whole mlx-serve suite: `53 failed, 205 passed` (the 53rd is the known `test_golden_first_pick_command_is_what_main_builds_for_the_same_registry`).
- stack (2 files): `26 failed, 9 passed in 0.42s`
- skipped: 0 everywhere.

Passing on baseline (all invariants / instruments, by design):
fork 19 — support ×5 (all instrument tests), kernels `test_instrument_todays_decode_copies_the_strided_state`, mode ×6 (`test_a3_mtp_verify_scan_still_refuses_quantized_kv_without_the_mode[4|4.0|8|2.5]`, `test_a3_mtp_verify_scan_native_and_draft_kind_rules_unchanged`, `test_joint_v1_classify_keeps_sending_turboquant_caches_to_per_query`), routing `test_mode_absent_native16_runs_with_the_shipped_policies`, memory `test_instrument_lazy_chain_holds_several_scratches_and_per_layer_eval_holds_one`, generation ×5 (`test_a3_*` four goldens + `test_a3_scenarios_are_deterministic`).
serve 5 — `test_fused_v1_with_kv_bits_4_is_refused_without_the_mode`, `test_joint_v1_with_kv_bits_4_is_refused_without_the_mode`, `test_command_is_byte_identical_without_the_key[extra0]`, `test_command_never_emits_the_flag_for_text_or_absent_key`, `test_shipped_native_combination_stays_valid_without_the_mode`.
stack 9 — `test_earlier_controls_are_unchanged`, `test_v7_and_v8_rows_stay_compatible`, `test_existing_variants_still_parse[×3]`, `test_driver_default_capacity_is_the_token_count`, `test_driver_keeps_the_variant_eval_spec`, `test_registry_pick_is_unchanged`, `test_registry_pick_keeps_its_native_policies`.

Failure causes on baseline (every one traced): fork — 239 ERRORs and 102 of the FAILs are `ModuleNotFoundError: No module named 'mlx_vlm.tq4_fast'` / `tq4_attention`; the other 3 FAILs are the CLI tests, `SystemExit: 2` (unrecognised `--tq4-attention`). serve — `TypeError: ModelConfig.__init__() got an unexpected keyword argument 'tq4_attention'`, `AttributeError`, or today's `ValueError ... requires kv_bits 0 (got 4)` where the relaxation is the subject. stack — `KeyError: 'tq4_attention'`, `DID NOT RAISE ServingStateError`, `assert 8 >= 9`, argparse `invalid choice: 'tq4_m72'` / unrecognised `--capacity`, docs lacking the key.

## Validation of the tests themselves (not baseline results)

- Kernel file run against a scratch shim (`../scratch/shim_plugin.py`, `run_with_shim.py`) that maps the `tq4_fast` interface onto the dev prototypes: `167 passed` — this validates the references, the A1 criterion, the negative controls (leak/drop fail, true call passes), the copy-free instrument and the long-context runtime (whole file 5 s). It says nothing about the production kernels.
- Model-level helpers (`pair`, `step` incl. verify commit, `greedy`, `mtp_run`, spies, memory harness) smoke-run with the mode absent (`../scratch/smoke_helpers.py`); the premises about the shipped native policies (prefill `force_fused=True`, verify = one `q_len=k` call with `mask="causal"`, decode one call) were observed on today's code.
- The A3 digests were first recorded in a plain process, mismatched pytest (TF32 pinned off by the fork conftest), and were re-recorded under that numerics; the four goldens pass under pytest on baseline in two separate runs.
- The model-level routing/generation/memory tests have NOT run against any implementation of the mode.

## Existing tests the change necessarily invalidates (not edited, not mine)
`benchmark/bench/tests/test_mtp_verify_scan_provenance.py:56` `assert P.FINGERPRINT_VERSION == 8` and `:60` `P._SERVING_CONTROLS == {...three controls...}`: both break at the version bump / new control.

## Ambiguities and untestable points (and how I read them)

1. `m72_exact` and `mtp_verify_scan.require_environment`: the load-order text says it accepts `kv_bits` 4 "iff the TQ4 mode resolved to `m72_v1`", but `m72_exact` also needs `joint_v1` on the native layer and mlx-serve requires `joint_v1` for either value. Read as "either value"; tests assert both accepted. If `m72_exact` is meant to be refused there, `test_mtp_verify_accepts_quantized_kv_when_the_mode_resolved[m72_exact]` is wrong.
2. Counter names: tests treat `route_counts()` as a flat dict keyed exactly by the table's names (`p2s`, `mma_prefill`, `d2`, `single_pass`, `mma`, `d2_verify`, `per_query:{short,k_gt_5,gapped}`, `native:{prefill,verify,decode}`, `fallback:<reason>`). Only `batch_cache` is a pinned fallback reason; every other fallback is asserted by prefix `fallback:`. Counter granularity (per layer per call vs per call vs per query) is not pinned: tests assert `> 0` and that no route outside the expected set moved (native counters and the per-query inner `d2`/`single_pass` allowed where the table says so).
3. Gapped lengths cannot be produced through the model (the verifier's per-query slices are always consecutive) and the dispatch hook's name is free, so the `per_query:gapped` row has no test. Same for through-the-model rows with an array mask, sinks, and `BatchTurboQuantKVCache` (the model never hands those to a TQ layer in a single-sequence call): their reasons are tested only at `supports` level (`batch_cache` pinned, others non-empty). If the hook is given a name, these three rows are testable directly.
4. How the mode reaches `base.py` is free, so tests never call `scaled_dot_product_attention` with a mode directly; all routing is through `apply_to_model` + a model forward.
5. Gapped/short contract of `verify_attention` at the kernel level: spec says k=2…5 consecutive, `lengths[0] > 2048` only for the exact path (R4 "asserts T > 2048"). Tests call `exact=True` only with `lengths[0] ≥ 2049`; out-of-contract arguments are asserted to raise `AssertionError` or `ValueError` (spec: "preconditions asserted").
6. Provenance names: the runtime key `tq4_attention` / `tq4_attention_source`, the default being whatever `_SERVING_CONTROLS["tq4_attention"][1]` says (must not be a mode), by analogy with the M57/M58 controls. The route-counter field in the manifest is "name free": no test pins it (only the `/health` details, found by value, are tested). `--tq4-attention` worker flag spelled as in the CLI section.
7. `check_fp16_range`: exception type and message free; tests require a raise, and that the message contains the offending layer index as a standalone number. The codebook bound is planted through the `caches` argument (the only way to reach a codec). Query bound boundary: `max|γ| = 1024` accepted (√256 · 1024 = 2¹⁴, "≤").
8. `m72_v1` has no length floor for `mma` in the table (only `m72_exact` has `lengths[0] ≤ 2048 → per_query:short`); tests follow the table (`test_v1_verify_block_below_2048_takes_mma`). Flag if v1 below 2,048 is meant to route elsewhere.
9. `apply_to_model` return value read like `mtp_verify_scan.apply_to_model`: the number of qualified attention modules (2 in the synthetic model, including the native one), not the TQ4 ones.
10. A4(c) "MTP OFF" is taken with the same mode applied (`m72_exact`) in both runs, same prefill; the stack-smoke parts (real model, 8K/32K, divergence diagnostic, A5, A6) are out of scope for these files.
11. Non-power-of-two RHT rotation (a `supports` clause) cannot be constructed from outside (D = 256 is fixed by the shape clause); untested.
12. "Exactly once per layer per chunk" evaluation is asserted only through its memory consequence (peak ≤ 2 scratches and `p2s` ≥ number of TQ4 layers); an extra evaluation would not be caught.
13. Test runtime on a working build is estimated, not measured: the kernel file takes 5 s against the shim; the generation file's A4(c) block runs 24 MTP generations of 256 tokens plus 3,000-token prefills.

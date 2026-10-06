# M58 — joint MTP verification scan for long-context decode (spec v3.2, 2026-10-06; C118: BUILD GO — in cold review)

Queue row: `docs/PLAN.md` M58 (C112). Evidence: `docs/proposal-flash-attention.md` E8, E11, P60, P69, X2, X9. Scope: first pick
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, native16 KV, MTP ON, shipped M57 state. Phase 2 serving optimization; no B/C
evidence. Registry of record does not change until the operator approves adoption. v1 was reviewed cold by Codex `gpt-6-astra`
(REVISE, S1–S11) and Claude (REVISE, S1–S14, with GPU identity checks on this box — `$STACK_WORKDIR/m58/claude_spec_review_1.md`);
v3 adopts every finding except where "Rejected review points" says otherwise. Build base commit: stack `64bea61` (the `sdpa`
row persistence this spec relies on is committed there), fork `fbe2775e`, router `7be6bfd`. Discussion ids P89–P97.

**Headline from review (Claude S1, VERIFIED on the M5 Max, device class `applegpu_g17s`):** the joint call is bitwise identical
to the per-query calls EXCEPT when a block's key range crosses an MLX key-length threshold (1024, 8192, 32768, 65536): MLX
picks one-pass vs two-pass and the two-pass `blocks` count per call from the key length, and a different block count is a
different summation order. The fork mirrors that choice in `qwen3_5/language.py::_qwen3_5_sdpa_vector_plan`. So "bit-identical"
is achievable only with a straddle rule (rule 7 below) — and the shipped `length == 2` joint branch is ALREADY non-identical at
those thresholds (C120, pre-existing, separate ruling).

## What changes (P89)

`mlx_vlm/models/qwen3_5/speculative_verifier.py::Qwen3_5BatchInvariantForward._attention`, branch `elif output is None and
length > 1` (verification blocks of length ≥ 3): today `length` calls of the fork's `scaled_dot_product_attention`, one per
query over a physically shortened key/value prefix, concatenated. Under `joint_v1` that branch makes ONE call over the full
keys/values with a 4-D boolean step mask — the construction the `length == 2` branch already uses in production. Same native
SDPA API, same `cache=` / `scale` / dtype / head layout, `policy` and `force_fused` never passed (the M57 policy rejects `qL ≤ 8`
anyway). One kernel launch per layer instead of `length`; still about one key/value pass per query (L2-shared), per E8 / P69 —
the single-pass kernel is out of scope. Identity: bitwise equal away from the MLX key-length thresholds (Claude S1, measured);
rule 7 keeps straddling blocks on the per-query path so the served numerics never change. Speed: the arms decide.
Nothing else changes: length 1, the left-padded / ragged path, quantized caches, the drafter, acceptance, rollback and
cache state keep their code verbatim (S6).

Policy `joint_v1` (default `per_query` = today) takes the joint branch iff ALL hold; otherwise the existing per-query code runs
with its exact arguments and call count:

1. `output is None` and `length >= 2` (C120 RULED 2026-10-06: the shipped length-2 joint branch is folded in — it already runs
   jointly and is non-identical at the thresholds, so rule 7 now protects it too; length 1 untouched);
2. native cache (no `bits` attribute), keys/values plain 4-D `mx.array`, batch 1;
3. `mask` is `None`, the string `"causal"`, or a 4-D `mx.array` of dtype `bool` whose last two extents are ≥ `length` and
   ≥ `key_length` (sliced to `[..., :length, :key_length]`, ANDed with the step mask). Additive (float) masks, 2-D / 3-D masks,
   any other string: per-query (S2);
4. `prefix_length = key_length - length >= 0`;
5. `length * (n_q_heads // n_kv_heads) <= V`, `V` = the fused vector kernel's query bound read from the MLX dispatch source
   pinned to the installed build (STEP 1); above `V`: per-query (S3);
6. dtype and shape inside the qualified domain recorded in STEP 1 (expected: bfloat16, head dim 256, GQA 6, GPU default
   device, device class `applegpu_g17s`). Outside it: per-query. fp16 is excluded unless STEP 1 measures it (S3);
7. no threshold straddle: `_qwen3_5_sdpa_vector_plan(prefix_length + 1, n_q, n_kv) == _qwen3_5_sdpa_vector_plan(key_length,
   n_q, n_kv)` (same pass mode AND same `blocks`). Otherwise per-query, counted as `verify_blocks_straddle` (Claude S1; at most
   `length − 1` rounds per threshold per request).

`joint_v1` refuses at load when `MLX_SDPA_BLOCKS` is set (libmlx honours it; the fork's mirror does not). The thresholds belong
to `joint_v1` + the pinned MLX build; any MLX bump reruns STEP 1 before the policy is served.

Step mask: `arange(key_length)[None,None,None,:] < (prefix_length + arange(length) + 1)[None,None,:,None]` — the per-query
prefix set expressed as a mask (the `length == 2` branch builds the same mask only for `"causal"`; it passes `None` through).
Constants, thresholds and the domain belong to the version name.

## Controls, plumbing, provenance (P90)

- Fork CLI `--mtp-verify-scan {per_query,joint_v1}` (default `per_query`) and `--mtp-verify-ab` (flag; gate instrument, see
  P91) → env handoff → resolved ONCE at load into an attribute on the model instance AND on the qwen3_5 attention modules the
  verifier receives (`_attention(self, attention, …)` reads `attention`); never on the module-level verifier singleton, never
  the environment at call time (S6).
- Non-default value on a family whose verifier has no joint branch, on a quantized-KV model, on a non-GPU default device, or
  without `--draft-kind mtp` (the same verifier serves suffix decoding — Claude S11): refuse at load, exit nonzero before READY.
  `--mtp-verify-ab` without `joint_v1`: same. Load-time self-test when the policy is `joint_v1` (M57 style, bounded under 30 s):
  joint vs per-query bitwise at the largest eligible length on 2048 keys (must be identical) AND one straddling cell (keys
  1023→1025 across the block: the mirror must PREDICT the mismatch — a known positive for the instrument); a raise, an
  unpredicted mismatch or a predicted mismatch that does not occur: exit nonzero before READY (Claude S6).
- Counters, unit = verification BLOCK per layer, scoped per request with the M57 snapshot/since pattern (the verifier is a
  module singleton — Claude S9), in the response `timings` and on the "Request completed" line ONLY when the policy is not
  `per_query` (response bytes unchanged under the default, as M57 F1): `verify_blocks_joint_v1`, `verify_blocks_per_query`
  (fell back inside the domain; reason histogram `verify_fallback_reasons`), `verify_blocks_straddle`, `verify_blocks_len1`,
  and under AB `verify_ab_blocks`, `verify_ab_mismatch`, `verify_ab_straddle_blocks`,
  `verify_ab_straddle_mismatch`. Every `verify_*` key is persisted by capacity and `generate` rows when sent.
- Router: `ModelConfig.mtp_verify_scan: str = ""`, `mtp_verify_ab: bool = False`; validated in `__post_init__` (``,
  `per_query`, `joint_v1`; `joint_v1` requires `draft_kind == "mtp"` and `kv_bits == 0`; `mtp_verify_ab` requires `joint_v1`);
  `_build_command` appends the flags only for non-default values.
- Stack: fingerprint v8 adds `mtp_verify_scan` to the runtime slice with values `per_query`, `joint_v1`, `joint_v1+ab`
  (AB is a distinct served mode and is fingerprinted, S7), observed from the worker command line when up (flags absent →
  `per_query`, source `worker`) else the registry (`mtp_verify_ab` never comes from the registry: `joint_v1+ab` rows are
  gate rows only). Per-control introduction versions in the normalizer — `{"attention_policy": (7, "auto"),
  "lazy_prompt_embeddings": (7, False), "mtp_verify_scan": (8, "per_query")}`; `control_of` returns `(default,
  "default-pre-v<N>")` when `fingerprint_version < N`. The existing docstring "no v7 manifest exists on disk yet" is false (the
  M57 qualification rows are v7): a naive v8 would make every v7 row incompatible, refuse resumes and let `--clean-stale`
  archive them (Claude S5). A v8 manifest with a missing or unknown value refuses everywhere (`compare`, resume,
  `assert_serving_state`). `compare.py` refuses across differing values; `compare_predictor._MUST_DIFFER_KEYS` gains the key.
- Stated limit (S8): the serving-path hash covers the whole fork tree, so the fork bump splits pre-/post-M58 rows for EVERY
  model served by the bumped fork, not only the first pick — expected, as at M57. No code-hash check is weakened. AC1 proves
  argument equality under the default; it does not prove unchanged performance for other models — a one-session default-path
  screen on the second pick (8K / 64K rungs, matched state) is part of qualification if that claim is made.
- Qualification runs the branch through a stack worktree whose `src/*` submodule pointers reference the branch commits, so
  `_git_shas` attributes the code correctly; PYTHONPATH runs are probes, never graded (S8).

## Gate-1 instrument (P91)

`--mtp-verify-ab`: every joint-eligible block computes BOTH paths from the SAME prepared queries/keys/values (QKV projected and
cache updated once), serves the JOINT output (the production path is what runs downstream — S4), and compares the per-query
output against it: shapes and dtypes equal; no non-finite values in either; bitwise equality of the raw representation
(`view(uint16)` for 16-bit dtypes; `array_equal` is not enough: −0 == +0, NaN ≠ NaN); mismatch flags accumulate lazily and are
read once per round (no per-layer `.item()`), materialised before the counters advance. Straddling blocks (rule 7) are
shadow-computed too, into `verify_ab_straddle_blocks` / `verify_ab_straddle_mismatch` — they are the LIVE known positive: the
mirror must predict every one of them. Any eligible-block mismatch increments `verify_ab_mismatch` and logs `(layer, length,
key_length, dtype, max_abs)` once per distinct shape. The AB joint call is the same function object as the production joint
call (AC7). Not a production mode; never in the registry.

## STEP 1 — evidence before any build (no model; CPU + one GPU microbench, unpiloted target ≤ 1 box-hour) (P92)

1. Pin the MLX dispatch source for the installed build (`mlx` 0.32.2 per `docs/specs/m57-qualification.md`; verify
   `mx.__version__` on the box): the `sdpa_vector` eligibility predicate in ml-explore/mlx
   `mlx/backend/metal/scaled_dot_product_attention.cpp` at the release tag. Record `V`, the mask forms it accepts (bool array,
   `"causal"`), and any dtype/head-dim/batch conditions. The installed wheel ships kernel headers only
   (`mlx/backend/metal/kernels/sdpa_vector.h`: the two-pass threadgroup is 32 × gqa × qL threads, so `V = floor(pipeline max
   threads / 32)` — 32 at a 1024-thread limit, 28 if the limit is 896 as the fork's `test_model_ops.py` records for some GPUs);
   the host dispatch is compiled. Without the pinned source the build does not start (Codex S3, Claude S6).
2. Extend `$STACK_WORKDIR/m57/sdpa_microbench.py` into `$STACK_WORKDIR/m58/verify_microbench.py` (workdir only): GQA 6, head
   dim 256, bfloat16 (and fp16 only if the first pick's cache dtype is fp16 — read it from the served worker's log); `qL ∈
   {3, 4, 5, 6}` × keys `{8192, 65536, 131072, 262144}`; arms: per-query over sliced prefixes (today's exact pattern), joint
   with the 4-D boolean step mask (the proposed path), joint with `"causal"` (reference only). Record ms, bitwise equality
   joint-vs-per-query per cell (not `max abs`), whether `qL = 6` changes kernel (timing cliff), and the 1-, 3-, 5-query
   per-layer times for the cost arithmetic. PLUS the threshold sweep (Claude S1): keys 1018–1030, 8188–8200, 32764–32776,
   65532–65544 at `qL ∈ {2, 3, 4, 5}`, recording per-query-position bitwise equality. Decision rule: build only if (a) the
   mirror `_qwen3_5_sdpa_vector_plan` predicts EXACTLY the mismatching cells (every straddle mismatches as predicted, nothing
   else mismatches), and (b) the boolean-mask joint call is faster at ≥ 65536 keys. Otherwise record the number and close M58.

## STEP 1 RESULT (2026-10-06 02:39 UTC, quiet box, 140 W, battery 100 %; `$STACK_WORKDIR/m58/verify_microbench.run1.json`, script `verify_microbench.py`)

MLX 0.32.2, `applegpu_g17s`, `MLX_SDPA_BLOCKS` unset; the script's copy of the plan mirror matches the fork's
`_qwen3_5_sdpa_vector_plan` on 14 probe lengths. bf16, GQA 6, head dim 256, synthetic arrays, 5 reps median.

- **(a) PASS — the mirror predicts exactly the mismatching cells.** Threshold sweep 208/208 cells exact (keys 1018–1030,
  8188–8200, 32764–32776, 65532–65544 × `qL ∈ {2,3,4,5}`): mismatches only at keys 1024–1028, 8193–8196, 32769–32772,
  65537–65540, always the first `qL − d` query positions, as rule 7 predicts; every other cell bitwise identical. Boolean step
  mask and `"causal"` string give the identical pattern. Main grid `qL ∈ {2..5}` × keys {8192, 65536, 131072, 262144}: all
  bitwise identical, all finite.
- **`V` confirmed empirically: `qL = 6` (6 × GQA 6 = 36 > 32) is NOT identical at any key length and is not faster** — the joint
  call leaves the vector kernel. Rule 5's bound is 32 on this box; `qL ≤ 5`.
- **(b) PASS — faster at ≥ 65536 keys.** Per layer, median ms, per-query → joint (bool mask) → joint (`"causal"`):
  65536: `qL 3` 1.82 → 1.47 → 1.39; `qL 5` 2.93 → 2.25 → 1.99. 131072: `qL 3` 3.42 → 2.70 → 2.50; `qL 5` 5.51 → 4.23 →
  3.72. 262144: `qL 3` 6.58 → 5.20 → 4.75; `qL 5` 10.89 → 8.73 → 7.35. Consistent with E8 (3.45 → 2.44 at 131072).
- **8192 keys: joint is NOT faster** (`qL 3` 0.306 → 0.325 ms, +6 %, +0.02 ms absolute per layer). Prediction for the 8K rung
  revised: decode within ±2 % (16 layers × 0.02 ms ≈ 0.3 ms of a ≈ 50 ms round); the arms measure it.
- **Mask-form amendment (measured, adopted):** the `"causal"` string is 5–16 % faster than the boolean step mask at every
  cell with the same identity pattern. Rule 3 becomes: incoming `mask` `None` or `"causal"` → joint call with `mask="causal"`
  (identical support when `key_length ≥ length`, rule 4); incoming 4-D boolean array → AND with the step mask. AC2/AC3 cover
  both forms.

Decision: STEP 1 passes both rules; the build is now the operator's call (C118, build held).

## Build status (2026-10-06)

Built by the Sonnet implementer on fork `m58-joint-verify`, router `m58-joint-verify`, stack worktree `m58-provenance`; cold
reviews round 1: Codex `gpt-6-astra` (fork BLOCKING, router SHIP, stack BLOCKING; B1–B12) and Claude (fork FIX-THEN-SHIP, router
SHIP, stack FIX-THEN-SHIP; F1–F9, R1, S1–S6) — both in `$STACK_WORKDIR/m58/`. Fix round in progress. Accepted implementer
judgement calls: 1–5, 7–9; rejected 6 (recheck the RESOLVED drafter) and 10 (AB finalisation on every exit path); the autouse
conftest provenance pin is rejected in favour of per-module opt-in. Known, documented: the continuous-batching `_step` path
reports no `verify_*` counters (same as M57's `sdpa_*`).

## Build (Sonnet implementer, M54 funnel; CPU tests only, no loads, no pushes, no submodule bumps) (P93)

Acceptance criteria — each needs a named test written first and watched failing:

- AC1 Default preservation: registry without the field → worker command line byte-identical to today; under `per_query` the
  verifier branch calls SDPA with exactly today's per-query arguments (mock asserts call count = `length`, the prefix slices
  and the sliced masks).
- AC2 Decision table: `length ∈ {1, 2, 3, 4, 5, V/gqa, V/gqa+1, 9}` × cache {native, uniform-quantized, TurboQuant} × mask
  {None, `"causal"`, 4-D bool, 4-D float additive, 2-D bool, other string} × GQA {6, 8} × batch {1, 2} × dtype {bf16, fp16,
  fp32} × key lengths {1024, 1025, 1026, 8193, 8194, 65537, 70000} (straddle cells, with the plan mirror stubbed per device
  class): `joint_v1` takes the joint branch exactly on the set defined by rules 1–7; every other cell runs today's code with
  today's arguments (call-count and argument assertions); counters, `verify_blocks_straddle` and `verify_fallback_reasons` match.
- AC3 (a) Mask exactness on CPU: for `length ∈ {3, 4, 5}`, `key_length ∈ {64, 1024}` and masks None / `"causal"` / 4-D bool,
  the joint step mask's true-set per row equals the per-query key prefixes exactly; causal-leakage test (a future-key
  perturbation never changes any query's output); all-masked-row and non-contiguous-prefix masks fall back. (b) Numerics on
  CPU: joint vs per-query `allclose` against an fp32 reference at a stated tolerance — the CPU fallback is NOT bitwise
  (Claude S3 measured 16/16 cells differing); bit identity is a GPU property established by STEP 1, the self-test and gate 1.
- AC4 Propagation: registry → `ModelConfig` → command line → instance and attention-module attributes → the branch → counters;
  two instances in one process with different policies dispatch per instance; the verifier singleton carries no state.
- AC5 Scope: diff touches `speculative_verifier.py` (qwen3_5), the attention-policy plumbing files, server timings/log, router
  config and stack provenance only; `nemotron_h` / `gemma4` / `lfm2` / `glm_moe_dsa` verifiers, the left-padded helper and the
  quantized branches are byte-identical to `main` (diff-scope test).
- AC6 Loud failure: unknown value (router `ValueError`, worker argparse); `joint_v1` with `kv_bits > 0` or `draft_kind != mtp`
  (router); unsupported family / non-GPU device (worker exits nonzero before READY); `--mtp-verify-ab` without `joint_v1`.
- AC7 AB instrument: both paths run from one prepared QKV; the SERVED output is the joint one; an injected mismatch
  (monkeypatched per-query fn) is counted and logged once per shape; shape/dtype inequality and non-finite values count as
  mismatches; the comparison is materialised before counting.
- AC8 Same-instance generation identity on a CPU micro-model with MTP ON: one seeded prompt under `per_query`; restore the
  target cache, drafter cache and RNG state; rerun under `joint_v1` (AB off, production path): emitted tokens, per-round
  acceptance sequence, hidden states handed to the drafter, and post-rollback cache state identical (S4, S6).
- AC9 Counters: present in `timings` (non-streaming and streaming session-cache path) and on the completion line only under a
  non-default policy; response bytes unchanged under `per_query`; per-request reset.
- AC10 Provenance: v8 manifests carry `mtp_verify_scan` + source; `joint_v1+ab` observed from the worker flags; pre-v8
  manifests read `per_query` / `default-pre-v8`; v8 manifests with a missing/unknown value refuse in `compare`, resume and
  `assert_serving_state`; worker/registry mismatch refuses; the A/B tool accepts the key; v1–v7 vs v8 and unknown-vs-unknown
  cases tested; capacity and `generate` rows carry every `verify_*` counter when sent (S7).
- AC11 `parity_replay` upgrades for G1b (Codex S5, Claude S4): refuses unless every frozen key is present exactly once in both
  replays and every response is well-formed (non-empty content or finish reason, usage present); records per request the
  payload+seed hash, `draft_rounds` / `draft_n` / `draft_n_accepted`, every `verify_*` counter, the v8 runtime slice and the
  worker command line (`--model` / `--draft-kind` / `--mtp-verify-scan`); sends the router's auth header when configured; M50
  at entry, C106 at exit; `compare` reports identical / differing / missing per key and exits nonzero on any missing key.
- AC12 v7 compatibility: a v7 manifest (`fused_v1`, no `mtp_verify_scan`) is compatible with a v8 `per_query` row and
  incompatible with a v8 `joint_v1` row; `--clean-stale` never archives a v7 row for the missing key.

## Qualification (operator session; design frozen before the first arm) (P94)

Machine-state protocol as `docs/specs/m57-qualification.md`: stack stopped, :8000 free, zero bench/worker processes verified by
executable and excluding the checker's own pid, 140 W / 28 V, battery > 20 %, 10 minutes idle before every arm-session with the
start state logged; one fresh lean router per arm-session (`MLX_VLM_CACHE_SESSION_MAX=1`, `APC_ENABLED` absent, verified on
router and worker pids); every runner smoked end to end on a real router (5 requests) before a long run; M50 at entry and C106
at exit on every runner, drift stamped on failure exits; a daemon monitor per run (`benchmark/m1/bench_watch.py` or
equivalent: progress, ETA vs prediction, errors, power each tick); worker command line (`--model`, `--draft-kind`,
`--mtp-verify-scan`, `--mtp-verify-ab`) recorded per arm-session; portable artifact paths.

**Pilot (first, ≈ 20 min, resizes everything below):** 5 seeded prompts at 8K and 128K under `joint_v1+ab`; record blocks per
round, ms per round, mismatch count, tokens emitted per request. Rung estimates are re-sized from mean/max + heavy-tail
allowance before the arms are queued.

**Gate 1 (identity) — must pass before any latency arm; any failure closes the build (strict identity is the stop; a
relaxation would be a separately approved lossy-lever qualification under AGENTS.md):**

- G1a Same-instance, production path served: worker under `joint_v1+ab`; `run_capacity` cold rungs 8192 / 65536 / 131072 /
  262144 (`--sampling-profile deployed`) plus the sustained-decode runner (below) at 65536 and 131072, plus four STRADDLE
  requests whose prompt length is ≈ T − 64 for T ∈ {1024, 8192, 32768, 65536} so the decode crosses each threshold (Claude
  S1). PASS iff `verify_ab_mismatch == 0` on every request, `verify_ab_blocks > 0` on every rung, `verify_ab_straddle_blocks
  > 0` and `verify_ab_straddle_mismatch > 0` on the straddle requests (the live known positive: the mirror predicted them),
  and an EMPTY `verify_fallback_reasons` histogram inside the domain (build judgement call 2, accepted by both reviews:
  the histogram counts only `per_query` fallbacks; `len1` and `straddle` are their own counters).
- G1b Cross-load: `bench.parity_replay` (AC11) on the first pick's C84 frozen 20 pairs under `per_query`, under `joint_v1`, and
  a same-policy reload control (`per_query` twice, separate loads). Decision: if the control is byte-identical, G1b requires
  20/20 identical content, reasoning and MTP counters across policies AND `verify_blocks_joint_v1 > 0` on ≥ 18/20 rows (proof
  the joint path ran). C120 carve-out (Claude build review 3, E1): a row whose joint-side `verify_blocks_straddle_len2 > 0` ran a
  length-2 block per-query where `per_query` used the shipped joint call, so its content MAY differ by design; such rows are
  listed separately as C120-expected divergence and do not fail G1b on content alone (everything else must still match). If the control itself differs (reload nondeterminism, `docs/metrics.md` 59–69), G1b is informative only
  and G1a decides; the divergence is recorded, not blamed on M58 (Codex S5, Claude S4).

**Latency (after gate 1):** arms A `per_query`, B `joint_v1` (AB off), same branch code, k=2 sessions each, order A→B then B→A.
Instruments (S9):

1. `run_capacity` cold rungs 8192 / 65536 / 131072 / 262144 — capacity, prefill, peak, counters (decode here is a 256-token
   screen only).
2. Sustained long-context decode, new workdir runner `$STACK_WORKDIR/m58/decode_probe.py` (M50/C106, derived timeout,
   retries 0, daemon): at 65536, 131072 and 262144 tokens of cached context, three paired seeded prompts per rung, deployed
   sampling, fixed generous thinking budget, minimum emitted tokens per request = pilot p50 rounds × 2.6 tokens (≥ 1024 target);
   per request: actual context, rounds, acceptance, emitted tokens, decode wall, `verify_blocks_*`. Primary endpoint: decode
   tok/s per rung, median over the three prompts, interval = bootstrap over prompts × sessions; MDE reported per rung from the
   pilot's spread. Completions shorter than the minimum are reported, not pooled.
3. Mechanism session (one, non-latency, after the arms): both arms under `MLX_VLM_MTP_PROFILE=1` at 131072, same prompts —
   verify ms per round per arm, the direct test of E11's 120 ms → ≈ 104 ms (Claude S7). Profiled rows stay in the workdir.

**Predictions on record:** from E8/E11 at 128K: per-round verification scans 16 × 3.45 = 55 ms (per-query) → 16 × 2.44 = 39 ms
(joint) of a 131.5 ms round → decode +14 % (E11); 256K ≈ +15 % (P69). 64K and 8K: no derivation in the evidence — HYPOTHESES
"+5…8 %" and "within ±3 %", to be replaced by the pilot's arithmetic (S10). Prefill, peak memory, acceptance, rounds per
token: unchanged. Red flags: acceptance or `draft_rounds` differing between arms on the same seed (a gate-1 escape); any rung
slower by > 3 %.

**Adopt (operator approval, PROVISIONAL) iff** gate 1 passes AND sustained decode at 131072 is faster by ≥ 8 % in both sessions
with the interval excluding 0 AND no rung or instrument slower by > 3 % IN BOTH SESSIONS at the same rung (the branch drift of
handoff leftover 5 is 1.4–3.6 %; a one-session dip is noise until repeated — Claude S7) AND prefill / peak within ±3 %. Adoption = publish fork
+ router branches, bump submodules, registry `mtp_verify_scan: joint_v1` with a PROVISIONAL note, refresh the decode citations
in `README.md` / `docs/campaign-results.md`, fingerprint note in `docs/serving-path.md`. Identity replaces quality
requalification; the M57 certification debt (handoff leftover 2) stays separate and runs on the FINAL state after M58.

## Cost (PRIORS, not pilot-sized; the pilot resizes them; basis stated) (P95)

- STEP 1: ≤ 1 box-hour (microbench: 4 key lengths × 4 query lengths × 3 arms × 5 reps at ≤ 7 ms each, dominated by setup) +
  CPU reading.
- Build: 0.5–1 day Sonnet + two cold review rounds (Claude, Codex `gpt-6-astra`) + the live smoke; `parity_replay` and the
  decode runner are part of the build.
- Pilot ≈ 20 min. G1a ≈ 4 rungs × (prefill + ≈ 2× verification) ≈ 45–70 min + the decode runner ≈ 30 min. G1b: 3 loads × 20
  replays ≈ 45 min.
- Latency: 4 arm-sessions × (10 min idle + load ≈ 3 min + 4 cold rungs ≈ 15 min + 9 sustained decodes ≈ 20 min) ≈ 3.2 box-hours
  (basis: M57's ladder averaged ≈ 35 min per arm-session, `docs/specs/m57-qualification.md`); mechanism session ≈ 40 min;
  optional second-pick default screen ≈ 40 min.

## Risks and what retires them (P96)

- R1 Vector-kernel bound / mask handling differ from E8's assumption → STEP 1 pins the source and measures; no build otherwise.
- R2 Per-query decomposition was deliberate (batch-invariant verification numerics) → gate 1, bitwise, production path served.
- R3 Scope creep into other verifiers → AC5 diff-scope.
- R4 Warm-state / order bias (E15) → order-balanced sessions, matched state, intervals, never one pair.
- R5 Branch-vs-shipped confound (handoff leftover 5) → both arms on the same branch code; correctly attributed via worktree.
- R6 AB mode changes timing or memory → `joint_v1+ab` rows are gate rows only, fingerprinted as such, never latency rows.
- R7 Counters change response bytes under the default → AC9.
- R8 Reload nondeterminism masquerades as an M58 defect → same-policy reload control in G1b.
- R9 Short completions make the decode screen noisy → sustained runner with a minimum emitted-token count from the pilot.
- R10 A threshold straddle slips through (an MLX bump moves a threshold; a device class with a different plan) → rule 7 uses
  the fork's mirror, the load-time self-test proves the mirror on the live device, `MLX_SDPA_BLOCKS` refuses, STEP 1 reruns on
  any MLX bump; AB straddle counters are the known positive on every gate run.

## Rejected or narrowed review points (P97)

- Codex S5 "cross-load divergence should trigger investigation, not close M58": adopted for G1b; G1a remains a hard stop.
- Codex S8 "add a matched default-path regression screen": adopted as optional-but-required-if-claimed (second pick).
- Claude S2 "let rule 7 cover `length == 2` under the same version": filed as C120 (pre-existing defect) and RULED
  2026-10-06 — folded in: rule 1 admits `length >= 2`, rule 7 protects it, the STEP 1 sweep, AC2 and the G1a straddle
  requests cover `length = 2`. Under `per_query` the shipped length-2 branch stays byte-identical to today.
- Claude S10 "under AB the served path is per-query": v2 chose to serve the JOINT output under AB (Codex S4) so the production
  path runs downstream during the gate; kept.

## Not in scope

Single-pass multi-query kernel (reads keys/values once; needs a custom kernel), dense prefill path, chunk sweeps, quantized-KV
picks, other model families. Each is a separate proposal.

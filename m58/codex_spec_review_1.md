**REVISE**

Scope: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. Read-only review; no tests, benchmarks, servers, or model loads.

**S1 — MAJOR — “What changes”: same API does not establish the same kernel.**

**VERIFIED:** Every verifier branch passes `cache=cache` and omits `policy` (`../mlx-vlm/mlx_vlm/models/qwen3_5/speculative_verifier.py:114–162`). Native dispatch therefore reaches ordinary MLX SDPA; quantized caches take separate branches (`../mlx-vlm/mlx_vlm/models/base.py:379–454`). Even if supplied, `fused_v1` rejects `qL ≤ 8` before its score-size rule (`../mlx-vlm/mlx_vlm/attention_policy.py:67–73`). **No M57 `force_fused` advantage exists for joint queries 3–5.**

**ASSUMPTION:** Identical selected kernels/reduction order. The installed header even contains a single-query, mask-free specialization (`.venv/lib/python3.12/site-packages/mlx/include/mlx/backend/metal/kernels/sdpa_vector.h:320–326`); its actual dispatch is unverified.

**Rewrite:** “Same native SDPA API; kernel selection and bit identity require verification. Preserve `cache`, scale, dtype, head layout and omission of `policy`/`force_fused`.”

**S2 — BLOCKING — Rule 3 / AC2–AC3: mask eligibility is incorrect.**

**VERIFIED:** Rule 3 admits any array with rank ≥4 and specifies AND (`docs/specs/m58-joint-verification-scan.md:20–21`). MLX supports boolean **or additive** masks, with **at most four dimensions** (`.venv/lib/python3.12/site-packages/mlx/core/fast.pyi:132–140`). Boolean AND cannot preserve additive biases.

**VERIFIED:** `"causal"` is lower-right aligned, so the proposed step mask matches its mathematical support when `key_length ≥ length`. That does not establish numerical identity against physically shortened prefixes: the current calls change key length for each query (`../mlx-vlm/mlx_vlm/models/qwen3_5/speculative_verifier.py:131–148`).

**Rewrite:** Initially admit only validated 4-D boolean masks, `None`, and `"causal"`; preserve the existing path for additive/unsupported masks. Require nonnegative prefix length and compatible extents. Test causal leakage, all-masked rows, noncontiguous prefixes, and key lengths around dispatch boundaries. Treat accumulation-order differences as **ASSUMPTION pending measurement**.

**S3 — MAJOR — Rule 4 / STEP 1: `V` remains unverified, and eligibility exceeds the qualification grid.**

**VERIFIED:** The installed package exposes API declarations and kernel headers, but the host dispatch implementation needed to establish `V` is absent; compiled kernel selection is not readable. Header constants such as `BN=32`, and template parameter `V` for value width, do **not** establish the proposed query bound (`…/sdpa_vector.h:15–46`). No numeric bound is verified here.

**VERIFIED:** The policy has no dtype, head-dimension, device, or batch restriction, while STEP 1 measures only bf16, GQA 6, dimension 256 (`docs/specs/m58-joint-verification-scan.md:16–23,53–57`).

**Rewrite:** Require a pinned dispatch-source citation matched to the installed build before finalizing eligibility; otherwise stop before implementation. Restrict `joint_v1` to the qualified device/dtype/shape domain. GPU-test fp16 separately or exclude it. Above the verified bound, retain the exact per-query calls; do not infer fallback behavior from timing or pass `force_fused`.

**S4 — BLOCKING — G1a / AC7 / AC10: the gate proves less than its name.**

**VERIFIED:** G1a compares attention tensors but serves the per-query tensor; AC10 explicitly tests that same old path (`docs/specs/m58-joint-verification-scan.md:38–41,77–85`). This is useful local equivalence evidence on observed inputs, but does not exercise the production joint result downstream.

**VERIFIED:** `mx.array_equal` tests values and permits differing dtypes—not byte identity (`.venv/lib/python3.12/site-packages/mlx/core/__init__.pyi:1272–1287`). The spec does not define synchronization, comparison completion, or coverage beyond one positive block count.

**Rewrite:** Assert shape/dtype, reject nonfinite outputs, compare integer views of raw representations, and materialize each comparison before counting success. Prepare/update QKV once; compare both attention computations against that same state. Record layer/shape coverage. Add a same-loaded-instance test that actually serves joint outputs from independently restored target cache, drafter cache and RNG state; compare tokens, hidden states, acceptance sequence and post-rollback state. Production AB-off execution must also be exercised.

**S5 — BLOCKING — G1b: current `parity_replay` cannot implement the specified gate.**

**VERIFIED:** It omits MTP counters (`benchmark/bench/parity_replay.py:105–111`), compares only intersecting keys, and returns success when that intersection is empty (`:131–152`). It does not require complete runs, matching seeds/payloads, or resolved serving-policy manifests. Malformed responses can become empty hashed strings (`:100–104`).

**VERIFIED:** The request routes exist on the current router (`../mlx-serve/src/mlx_serve/main.py:108`; `router.py:303`). Thus this is not a missing-endpoint problem. Authentication is conditional, while replay sends no authorization header (`router.py:50–59`; `parity_replay.py:41–46`). Live usability was not tested.

**VERIFIED:** Recorded reload nondeterminism invalidates attributing every cross-load mismatch to M58 (`docs/metrics.md:59–69`).

**Rewrite:** Explicitly fund instrument changes: exact 20-key coverage, unique keys, valid responses, payload/seed hashes, required counters, policy/code provenance and completion/drift checks. Add same-policy reload controls. Cross-load divergence should trigger investigation, not automatically close M58; same-instance production-path identity remains decisive.

**S6 — MAJOR — Scope / counters / downstream invariance: define the boundaries mechanically.**

**VERIFIED:** Length 2 already runs jointly; left-padding handling precedes both branches (`../mlx-vlm/mlx_vlm/models/qwen3_5/speculative_verifier.py:103–130`). The helper handles positive padding separately (`../mlx-vlm/mlx_vlm/models/qwen3_5/language.py:764–817`). “Everything else per-query” is therefore inaccurate.

**VERIFIED:** Acceptance uses target tokens or logits projected from hidden states (`../mlx-vlm/mlx_vlm/speculative/mtp.py:458–491`). The drafter also consumes verified **hidden states**, and rollback commits retained cache prefixes—not merely logits (`../mlx-vlm/mlx_vlm/speculative/drafters/qwen3_5_mtp/qwen3_5_mtp.py:246–281`; `../mlx-vlm/mlx_vlm/speculative/cache_state.py:216–227`). The verifier itself is a module singleton (`../mlx-vlm/mlx_vlm/models/qwen3_5/language.py:25`).

**Rewrite:** Preserve existing length-1/2, padded and quantized branches verbatim. Define counters as blocks or SDPA calls consistently; distinguish M58 joint blocks from legacy joint blocks and AB shadow calls. Test exact fallback arguments/counts, mixed acceptance/rollback, per-request reset, and isolation between model instances; never store policy on the shared verifier singleton.

**S7 — BLOCKING — Provenance v8: AB execution is a distinct served mode.**

**VERIFIED:** AB-on advertises `joint_v1` while serving `per_query`; only R6 says the manifest records the environment (`docs/specs/m58-joint-verification-scan.md:38–45,138`). Merely recording an unfingerprinted field does not prevent pooling.

**VERIFIED:** Current control normalization hardcodes introduction at v7 (`benchmark/bench/provenance.py:556–571`); compatibility negotiates the minimum version and has a v1 return (`:397–427`).

**Rewrite:** Add per-control introduction versions: M58 defaults only before v8; missing/unknown v8 values refuse everywhere. Fingerprint observed, load-resolved AB mode—or make AB artifacts categorically unpoolable. Test v1–v7 versus v8, unknown versus unknown, resume, ordinary comparison and every A/B mode. Extend both runtime assembly and `assert_serving_state`; preserve `ServedConfigError` propagation and exact worker attribution.

**S8 — MAJOR — Provenance / R5: default preservation does not preserve historical comparability.**

**VERIFIED:** Serving hashes cover the whole fork serving tree, not the active model’s branch (`benchmark/bench/provenance.py:156–185`). Both comparison tools reject changed hashes (`benchmark/bench/compare.py:233–250`; `compare_predictor.py:123–141`). Other models on default policy will therefore also split across the fork bump.

**VERIFIED:** Qualification via a sibling checkout can stamp the wrong code: `_git_shas` hashes `src/*`, not arbitrary `PYTHONPATH` implementations (`benchmark/bench/provenance.py:1602–1615`).

**Rewrite:** State these limits explicitly. Keep A/B on identical, correctly attributed code; specify how qualification deploys it before adoption. Do not weaken code-hash checks globally to recover default comparability. Add a matched default-path regression screen if claiming unaffected performance for other models; AC1’s argument equality cannot establish that.

**S9 — MAJOR — Qualification: retain cold rungs, add a sustained decode instrument.**

**VERIFIED:** `run_capacity` imposes 256 maximum output tokens **and thinking budget 256**; it does not guarantee 256 emitted tokens (`benchmark/bench/run_capacity.py:124–125`). M57’s 100/600/5000 continuation sizes describe **added prompt tokens**, not output lengths (`docs/specs/m57-qualification.md:35–36`). E11’s verification share is 120/131.5 ms, approximately 91% (`docs/proposal-flash-attention.md:467–471`).

**ASSUMPTION:** One short decode per rung resolves an 8% benefit and a 3% regression threshold.

**Rewrite:** Use cold rungs for capacity/prefill and a separate cached long-context decode measurement with a pilot-sized minimum emitted-token/round count, fixed generous thinking budget and paired prompts/seeds. Record actual context, round counts, acceptance, decode time and verification time. Keep AB profiling outside latency arms. Pre-register repetitions, aggregation, intervals/MDE and handling of short completions; retain A→B/B→A and power monitoring throughout.

**S10 — MAJOR — Evidence claims: correct the mechanism and narrow identity claims.**

**VERIFIED:** “Reads … once instead of `length` times” (`docs/specs/m58-joint-verification-scan.md:13–14`) contradicts P69 and the spec’s own exclusion of a true single-pass kernel (`docs/proposal-flash-attention.md:444–447`; spec `:143–144`).

**VERIFIED:** E8 reports synthetic bf16 identity at lengths 3 and 5; it does not document the full proposed boolean-mask/prefix-slicing matrix (`docs/proposal-flash-attention.md:385–387,419–422`). The +14%/128K and +15%/256K predictions accurately reproduce E11/P69 estimates. P60’s approximately 2× prediction was superseded. The 64K +5–8% and 8K ±3% predictions lack a stated derivation.

**Rewrite:** “One SDPA invocation replaces several; physical read reduction and kernel identity are unverified. E8 motivates testing, not served-path identity.” Show the round-cost arithmetic and label unsupported rung predictions as hypotheses.

**S11 — MINOR — Cost / operational acceptance: executable details remain missing.**

**VERIFIED:** The heading says “sized from the seeded pilot,” but that pilot is future work; ≤1 hour is an upper target, not a lower bound (`docs/specs/m58-joint-verification-scan.md:119–126`). Neither named runner implements `--limit 5`, and `run_capacity` lacks the proposed 2000-token output control (`benchmark/bench/parity_replay.py:155–160`; `run_capacity.py:40–55,124–125`).

**Rewrite:** Call present costs unpiloted estimates; itemize prefill, decode, loads, cooldowns, reload controls and reviews, then resize from measured mean/max plus tail allowance. Specify actual five-request smoke commands and the long-continuation runner. Require daemon/power logs, M50 before I/O and C106 on failure exits, portable artifact paths, and explicit in-turn push approval (`AGENTS.md:45–53`). Retain the strict identity stop: any intentional relaxation becomes a separately approved lossy-lever qualification under `AGENTS.md:59`.

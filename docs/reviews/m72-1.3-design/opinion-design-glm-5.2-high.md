I have completed my investigation. Here are my findings.

---

# Cold Design Review — SPEC.md (M72 1.3)

## F1 — A5 memory bound is unachievable as written (cap-sized scratch mismatch)
**Location:** SPEC.md §Acceptance criteria A5 (lines 145–146); settled constraints §"Scratch size = the state's capacity" (lines 75–76).
**Severity:** major.
**Evidence:** confirmed.

The production path preallocates KV capacity to the max context (`kv_prealloc_tokens = max_kv_cache_size = 262,144`, registry `main_models.excerpt.yaml` lines 6–7; AGENTS rule). The spec fixes the scratch at "the state's capacity (cap-sized)". So the p2s scratch in production is sized to **262,144** tokens.

A5's comparator is the dev harness `tq4_p2s:layer` at 131,072 tokens (`benchmark/results/m72/e2e/`). The harness builds `TurboQuantKVCache(bits=4, max_kv_size=N, prealloc_tokens=N)` with `N = a.tokens = 131,072` (`m72_e2e_prefill.py:71`), and `dequant_rotated` emits output shape `(1, n_kv, cap, D)` with `cap = keys.norms.shape[2] = N = 131,072` (`m72_scratch_prefill.py:118–121`). So the dev harness scratch is sized to **131,072**.

Scratch = 2 (K+V) · n_kv(4) · cap · D(256) · fp16(2 B):
- dev harness (cap 131,072): ≈ 0.54 GB
- production (cap 262,144): ≈ 1.07 GB
- difference: ≈ 0.54 GB

A5 bounds the production peak delta at `4.30 + 0.40 (layer‑63 native16‑minus‑TQ4) + 0.25 scratch = 4.95 GB`. The production peak, however, is `4.30 (dev) + 0.54 (scratch‑size delta) + 0.40 (layer 63) ≈ 5.24 GB`. The 0.25 GB slack is ~0.29 GB short of the real scratch‑size delta alone.

**Failure scenario:** the implementer follows the spec literally (cap‑sized scratch, per‑layer eval, layer 63 native16) and runs A5 at 131,072 on the real model. The OS‑ledger peak delta lands near 5.2 GB; A5's 4.95 GB ceiling fails; the build is rejected for a memory regression that is actually a measurement‑baseline mismatch, not a defect.

**Proposed change:** Either (a) re‑run the dev harness `tq4_p2s:layer` comparator at `--tokens 262144` so the scratch sizes match, and drop the `+0.25 scratch` slack; or (b) add the scratch‑size delta explicitly: `… + (scratch(cap=max_ctx) − scratch(cap=131072))` ≈ `+0.54 GB`, and keep a small slack. State which cap A5's comparator uses.

---

## F2 — A6 fallback counter is ambiguous for k > 5 / gapped verify blocks
**Location:** SPEC.md §Routing table (lines 67–69), §A6 (line 148), §"Per‑call fallbacks … counted" (line 116).
**Severity:** major.
**Evidence:** confirmed (code path) + hypothesis (classification).

The routing table lists "verify, k > 5 or gapped lengths → today's per‑query loop" as a first‑class regime, but §"Per‑call fallbacks" says only "out‑of‑scope caches are counted". A6 requires "the fallback counter = 0 for in‑scope calls". Two competent implementers read this differently:

- **Reader A:** k > 5 / gapped is a *regime* (a row of the routing table), not a fallback; the counter tracks only out‑of‑scope *caches* (wrong codec/shape/batch). Then A6 passes even if every verify block has k = 6.
- **Reader B:** k > 5 / gapped is a *fallback* (the in‑scope cache took today's path instead of mma). Then a drafter configured with block_size > 4 increments the counter on every round and A6 fails.

The drafter's `block_size` (which sets k = bs = block_size + 1) is loaded from `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter` and is not constrained anywhere in SPEC.md. If that drafter's configured depth is > 4, k > 5 occurs in normal MTP rounds.

**Failure scenario:** the shipped drafter has `block_size = 4` (k = 5, mma used) today, but a future drafter reload or a `--draft-block-size` override raises k to 6. Reader A's build silently never uses mma (always per‑query) and reports counter = 0; Reader B's build reports counter > 0 and fails A6. Same spec, opposite outcomes.

**Proposed change:** State explicitly whether k > 5 / gapped counts as a fallback, and add a precondition (or an A6 check) that the loaded drafter's effective block size ≤ 4 so mma is the served verify path. Without that, "the mode exists end to end … every regime routes as specified" is untestable for the verify regime.

---

## F3 — R1 fp16 range check ignores the value‑codec inverse rotation and the SDPA fp16 path
**Location:** SPEC.md §"R1 fp16 query range" (lines 82–88); `tq4_attention.check_fp16_range` interface (line 108).
**Severity:** minor (safety net likely never trips on this model) but the *rationale* as written is incomplete.
**Evidence:** confirmed.

The bound `|q′| ≤ √D · max|γ|` is correct for the **key‑codec‑rotated query** that enters SDPA (`key_codec.prepare_queries` = RHT, orthogonal; `q_norm` is RMSNorm with `√D` gain; RoPE/MRoPE is orthogonal). I traced `Qwen3_5Attention._prepare_projected_qkv` (`language.py:1030–1075`) and `q_norm = nn.RMSNorm(head_dim)` (`language.py:953`): the bound holds.

However, the spec justifies the bound only by "the rotations are orthogonal and q passes q_norm". The fp16 path that R1 guards is not only `prepare_queries` (query side) but also the **SDPA output before `_rotate_inverse`**: p2s does `cache.value_codec._rotate_inverse(o.astype(mx.float32))` (`m72_scratch_prefill.py:153`) — the inverse rotation is done in **fp32**, so it is not fp16‑bound. But the SDPA itself runs on fp16 K/V (the scratch) and fp16 rotated queries (`force_fused=True`); its fp16 output `o` is what gets inverse‑rotated. The bound therefore needs to cover the SDPA inputs (q′, K_rot, V_rot), and K_rot/V_rot come from `codebook[idx] · norm` in fp32→fp16 (one rounding), **not** from `q_norm`. The bound on q′ is fine, but the spec presents R1 as if `q_norm` is the only thing that matters; the codebook centroids and the fp16 K/V scratch are unbounded by `q_norm.weight`. The check is a useful gate, but its stated derivation is narrower than the fp16 surface it claims to cover.

**Failure scenario:** an implementer reads R1 as "q_norm.weight is the only fp16 risk" and, for a future codec with large centroids, trusts the check although it never inspects `key_codec.codebook`/`value_codec.codebook`. No wrong output today (the check would still pass on this model), but the safety net's scope is mis‑documented.

**Proposed change:** Either (a) state that R1 covers only the query‑side fp16 path and that K/V are fp32‑multiplied‑then‑rounded (so the codebook/norm products are the fp16 risk, separately bounded by the codec's construction), or (b) extend `check_fp16_range` to also bound `max|codebook| · max|norm|` for K/V and document that. As written, "covering RoPE / gate round‑off" overstates what `q_norm.weight` bounds.

---

## F4 — D2 bit‑identity is asserted by block‑count match, which is necessary but not sufficient
**Location:** SPEC.md §Routing (line 65), §"D2 keeps production's block count (`production_num_blocks`) so its result stays bit‑identical" (line 80–81); `dev/m72_mq_decode.py:24–33, 160–169`.
**Severity:** minor.
**Evidence:** confirmed.

`production_num_blocks` (`m72_mq_decode.py:24–33`) reproduces production `decode_attention`'s `num_blocks` for the **non‑legacy** 2‑pass path (`turboquant.py:6327–6334` with the `* heads_per_group` factor). Matching block count is necessary for bit‑identity, but the spec's wording "so its result stays bit‑identical" implies it is sufficient. It is not: D2's `mq_pass1_kernel` is a different kernel from production's `_fused_mse_decode_2pass_1_kernel`; bit‑identity also requires the same per‑(query, head, block) arithmetic order, which the prototype's docstring claims ("the singleton's expression sequence verbatim") but the spec does not re‑state as a requirement.

Additionally, if `TQ_DECODE_2PASS_LEGACY=1` is set (`turboquant.py:6540–6551`), production uses the **legacy** pass‑1 with a *different* block count (no `* heads_per_group`), so `production_num_blocks` no longer matches production and D2 is not bit‑identical to the then‑served singleton. The spec does not mention this env var.

**Failure scenario:** an operator sets `TQ_DECODE_2PASS_LEGACY=1` for an A/B measurement (the flag exists for exactly that). With the mode on, D2 (non‑legacy block count) and the singleton (legacy block count) diverge; A4's "MTP OFF greedy decode on TQ4 is token‑identical to today's TQ4 MTP OFF" fails, or silently produces different tokens if A4's comparator also runs under the legacy flag.

**Proposed change:** (a) restate the bit‑identity contract as "D2 replicates the singleton's per‑(query, head, block) arithmetic order; block count is matched to the served singleton's", and (b) make `require_environment` (or `supports`) refuse the mode when `TQ_DECODE_2PASS_LEGACY=1`, or document that D2 is only bit‑identical to the non‑legacy singleton.

---

## F5 — Verify k = 1 routing is reachable but only through the commit‑pending path; the table reads as if it is a normal MTP verify row
**Location:** SPEC.md §Routing (line 67: "verify, k = 1 | one query | as plain decode | bit‑identical").
**Severity:** minor.
**Evidence:** confirmed.

Normal MTP verify blocks always have length `bs ≥ 2` (`_mtp_next_block_size` returns `bs`, and `if bs <= 1: break` in `speculative/mtp.py:763`). The only width‑1 verify is `_mtp_commit_pending_token` (`mtp.py:633–642`), which calls `_mtp_verify_target` with a single‑token input; that flows through `speculative_verify_hidden` → `Qwen3_5BatchInvariantForward._attention` with `length = 1`, where `verify_policy.attend` returns `None` (`classify` → `len1`) and the verifier falls to `scaled_dot_product_attention` (`speculative_verifier.py:155–161`) → the TQ branch in `base.py` → `decode_attention`. So k = 1 verify is reachable, and the mode's base.py hook (D2 / single‑pass) does serve it. The routing is correct.

The finding is only that the row is labeled "verify, k = 1" as if it were an MTP verify regime; an implementer could waste time looking for a normal MTP round with k = 1 and not find one, then mis‑route by treating k = 1 as out‑of‑scope.

**Proposed change:** relabel the row "verify / commit‑pending, k = 1 (width‑1 verify)" and note it arrives through `_mtp_commit_pending_token`, so the implementer tests it via that path, not via a normal MTP round.

---

## F6 — `supports(cache, queries)` is the sole scope gate but its predicate is unspecified
**Location:** SPEC.md §Interfaces `supports(cache, queries) -> bool` (line 111); §"any other cache or shape falls back … per call, silently" (lines 48–49).
**Severity:** minor.
**Evidence:** hypothesis (interface underspecified).

The spec lists the in‑scope shapes ("batch 1, TurboQuant MSE 4‑bit keys and values, power‑of‑two RHT, head dim 256, 24 q / 4 kv heads (R = 6)") and says `supports` is "the scope test, no side effects". But the predicate is not written out. Two implementers could differ on: whether `supports` inspects `cache.key_codec`/`value_codec` types (`_TurboQuantMSECodec`) vs only `bits`; whether it checks `queries.dtype` (bf16 only? the mma `FRAGMENT_TYPES` and p2s both feed bf16 queries); whether it checks `queries.shape[-1] == 256` and `n_q/n_kv == 24/4`; whether it checks the mask form (p2s forces `mask="causal"`; a 4‑D boolean mask from left padding would not be served). The fallback is "silent, counted", so a too‑narrow `supports` silently regresses performance and a too‑wide `supports` silently violates A1.

**Failure scenario:** implementer A's `supports` checks only `isinstance(cache, TurboQuantKVCache) and bits==4`; a `prod`‑mode key codec (`TQ_KV_QUANT_MODE=prod`, `turboquant.py:6528`) passes the gate and reaches p2s/mma, which assert MSE‑only (`m72_scratch_prefill.py:88–92`, `m72_mma_verify.py:308–310`) and raise at request time — not a silent fallback, but an uncaught assert in a served arm. Implementer B's `supports` checks codec types and falls back silently.

**Proposed change:** write `supports` as an explicit predicate: `isinstance(cache, TurboQuantKVCache) and isinstance(key_codec, _TurboQuantMSECodec) and isinstance(value_codec, _TurboQuantMSECodec) and key_bits==4 and value_bits==4 and batch==1 and head_dim==256 and n_q==24 and n_kv==4 and queries.dtype==bfloat16 and mask in (None, "causal")`. Then the fallback counter and A2 are unambiguous.

---

## F7 — Scope request: pin the loaded drafter's effective block size
**Location:** SPEC.md §"verify, k ≥ 2 | k ∈ 2…5" (line 68); A6 (line 148).
**Severity:** scope request (no severity).

The mma kernel and the verify routing assume `k ∈ 2…5`. `k = bs = draft_block_size + 1` is determined by the loaded MTP drafter's config and the adaptive `_mtp_next_block_size` (`mtp.py:548–559`). The spec does not constrain it. If 1.4 certifies MTP ON vs OFF, the certified arm must use a drafter whose effective `bs ≤ 5`, or mma is never the served verify path and the speed projection (1.10× / 1.19×) does not apply. Recommend adding a precondition (or an A6 assertion) that the drafter's `block_size ≤ 4` for the `m72_v1` arm.

---

## F8 — Scope request: state the layer‑63 prefill/decode policy interaction with `fused_v1`
**Location:** SPEC.md §"native layer 63 | `KVCache` | `fused_v1` prefill, `joint_v1` verify, SDPA decode" (line 71).
**Severity:** scope request (no severity).

`attention_policy: fused_v1` is stamped on **all 16** full‑attention modules by `_apply_attention_policy_from_env` → `apply_to_model` (`generation.py:185–189`; `mtp_verify_scan.apply_to_model:548–560` stamps every qualified module). The spec says layer 63 gets "fused_v1 prefill … SDPA decode". For the 15 TQ4 layers, the base.py TQ branch returns before the policy check (`base.py:402–444`), so `fused_v1` is irrelevant there. For layer 63 (native), the policy is live. This is consistent, but only because the TQ branch precedes the policy branch. The spec should state that the mode does **not** unstamp `fused_v1` from the TQ4 layers (it is simply never consulted there), so an implementer does not "clean up" by stripping the policy from TQ4 modules and accidentally change layer 63.

---

## Summary

Blockers: none. Majors: F1 (A5 memory bound unachievable), F2 (A6 fallback counter ambiguous). Minors: F3, F4, F5, F6. Scope requests: F7, F8.

The routing table, the layer‑63‑native‑16 invariant, the R1 bound on the query side, and the load‑time refusal order are all consistent with the snapshot. The two material risks are both in the acceptance criteria, not the design: A5's comparator uses a different scratch cap than production, and A6's "fallback counter = 0" is undefined for the k > 5 / gapped regime thatthe spec itself routes to today's path. Fixing those two criteria (F1, F2) and tightening `supports` (F6) and the D2 bit‑identity wording (F4) would make the spec implementable‑to‑the‑letter and testable as written.

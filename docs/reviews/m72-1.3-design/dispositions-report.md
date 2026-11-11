# M72 1.3 — cold design review (strict), round 1 of 3: finding ledger, designer's dispositions

Spec `docs/specs/m72-1.3-tq4-production.md` v1 (`a34c2d65`) → v1.1 (findings applied once, not re-reviewed). Mode: opinion,
context `briefed` (the spec + copied fork / mlx-serve sources at fork `608e33ac`, mlx-serve `1ddf6f8`, stack specs / ledgers /
results / harness / registry excerpt; brief `brief-design-r1.md`). Dispatched 2026-11-11, all at once, read-only, 1,800 s timeout.

| member | runtime | model (as reported) | session | context | status | raw |
|---|---|---|---|---|---|---|
| sol | cursor-agent `--mode ask` | `gpt-5.6-sol-high` (id resolved from `--list-models`; unverified alias) | unreported | briefed, user instructions unconfirmed | rc 0, valid | `opinion-design-gpt-5.6-sol-high.md` |
| glm | cursor-agent `--mode ask` | `glm-5.2-high` (same) | unreported | briefed, user instructions unconfirmed | rc 0, valid | `opinion-design-glm-5.2-high.md` |
| sonnet | `claude -p`, tools Read / Grep / Glob, setting sources none | `claude-sonnet-5-5` | `be578835-0271-446c-9f18-d3104bffa0ef` | briefed | rc 0, valid | `opinion-design-claude-sonnet-5.5.md` |

Sonnet shares the designer's vendor (removes anchoring only). No member saw another's findings.

Designer's checks before judging (source, fork `608e33ac` / mlx-serve `1ddf6f8`): `_speculation_fallback_reason` returns
`mtp_batched` for `draft_kind == "mtp"` (`generate/ar.py:1486`); chat-id'd requests run `_process_cached_request` inline with
`_inline_draft_kwargs` (`server/generation.py:1830–1914`); `config.py:175` refuses `fused_v1` with `kv_bits != 0`; the fork's
`attention_policy.py` has no `kv_bits` refusal; `base.py:407` passes the caller's `keys_state` to `decode_attention`; decode
block tiers include `total_tokens <= 65536` (`turboquant.py:6329`); `SWEEP.md` k = 3 at 512 tokens per block: 1.575 / 2.683 ms.

| # | finding | by | severity (designer) | disposition | reason / change |
|---|---|---|---|---|---|
| 1 | A5 compares peak memory at different capacities (harness capacity = prompt 131,072; production 262,144): cache + scratch ≈ +3.5 GB vs a 0.65 GB allowance | Sol P5 (blocker), GLM F1, Sonnet F3 | major | adopted | criterion error, not a design error; A5 now measures both legs at capacity 262,144 (harness `--capacity`), bound = matched dev leg + layer-63 bytes + 0.25 scratch |
| 2 | mlx-serve refuses `fused_v1` with `kv_bits != 0`; layer 63's `fused_v1` prefill unreachable | Sol P4, Sonnet F1 | major | adopted | confirmed `config.py:175`; `fused_v1` / `joint_v1` valid with `kv_bits: 4` only with `m72_v1`, and `m72_v1` requires both |
| 3 | fork `mtp_verify_scan.require_environment` refuses `kv_bits`; edit and load order unspecified | Sonnet F2 | major | adopted | load order and the exact relaxation specified; refusal unchanged when the mode is absent |
| 4 | D2 deriving T from `cache.offset` reads later draft tokens in the per-query fallback | Sol P1 | major | adopted | T_eff from the passed `keys_state` everywhere; A1 / A2 rows on a sliced state |
| 5 | legacy decode flag / block override changes the singleton's partition → D2 identity breaks | Sol P7, GLM F4, Sonnet F6 | major | adopted | `require_environment` refuses with `TQ_DECODE_2PASS_LEGACY`; `supports` excludes overrides; contract restated as arithmetic order + block count |
| 6 | mask / sinks not in the scope test; array masks silently treated as causal | Sonnet F5, F6; GLM F6 | major | adopted | explicit `supports` predicate (class, codecs, bits, shapes, dtype, mask, sinks, flags) with counted reasons |
| 7 | the server path: non-session requests use continuous batching (MTP disabled, batch caches even at B = 1); counters could be vacuous | Sol P2, P3 | major | adapted | the mode serves the inline cached-session path (where MTP runs); batch caches fall back with reason `batch_cache`; speculation on the batching path is a non-goal; A6 is a served-path smoke with chat-id'd requests and non-zero route counters |
| 8 | correctness gates stop at 40,960; > 65,536 block tier and the 512 plan untested at target context | Sol P6 | major | adopted | A1 at 65,537 / 131,072 / 260,096 (D2 also 2,049–40,000) with caches preallocated to 262,144 |
| 9 | fallback counter semantics ambiguous (k > 5 / gapped: regime or fallback?) | GLM F2; Sonnet F7 | major | adopted | per-route counters with names and reasons; A6 gates `p2s` / `mma` / `native:*` > 0 and `fallback:*` = 0, records `per_query:*` |
| 10 | A4 "identical prefill state" is unconstructible with a load-stamped mode | Sonnet F4 | major | adopted | same-process construction: mode-off prefill, snapshot, decode off vs restore + apply mode + decode; prefill compared by tolerance |
| 11 | R1 derivation covers the query side only | GLM F3 | minor | adapted | K / V side stated (centroids in [−1, 1] × fp16 norm) and checked at load (max\|codebook\| ≤ 1) |
| 12 | SWEEP figures misstated; "measured at k = 3 only" false | Sol P8 | minor | adopted | −8 % / −15 % at k = 3; k = 1 / 5 swept; A1 re-established on the 512 plan |
| 13 | "verify, k = 1" row reads as a normal MTP round | GLM F5 | minor | adopted | relabelled width-1 verify (`_mtp_commit_pending_token`) |
| 14 | an implementer could strip `fused_v1` stamps from TQ4 modules | GLM F8 (scope request) | — | adopted as clarification | no scope change: stamps stay, inert on TQ4 layers |
| 15 | layer 63 may silently fall back when not stamped | Sonnet F7 | minor | adopted (with 2) | `m72_v1` requires both stamps at load; `native:*` counters |
| S1 | pin the drafter's effective block size ≤ 4 (k ≤ 5) | GLM F7 | scope request | → operator | rec: no pin in 1.3 — k > 5 routes to the per-query loop and is counted; 1.4 reports the k distribution |
| S2 | short prefill chunks (L 2–5, e.g. a turn's tail) pay a capacity-sized dequantize | Sonnet F8 | scope request | → operator | rec: route non-verify L ≤ 5 at T_eff > 2048 through the verify kernel with consecutive lengths (same causal semantics, no scratch); measure in 1.4 |
| S3 | speculation on the continuous-batching path | Sol P2 (alternative) | scope request | → operator | rec: no (non-goal; the certified traffic is chat-id'd) |

Opposing views: none between members on a shared finding. Driver-only concerns: none added.

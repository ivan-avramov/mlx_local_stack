# P369 — MTP certification: prove exactness, fix M2–M5 (PLAN v2, 2026-10-17)

Status: PLAN v2 (Cursor `gpt-5.6-sol-high` plan review round 1: AGREE WITH CHANGES Q1–Q10, all applied;
`docs/reviews/p369-plan-round1.cursor-gpt-5.6-sol-high.md`) → round 2 confirmation → execute.
Origin: P368 layer 1 (`docs/reviews/p368-layer1-mtp-mechanism.cursor-gpt-5.6-sol-high.md`, NOT NEUTRAL M3 M4).
Both B picks ship `draft_kind: mtp`. Claim being certified: **MTP-ON output is distributed exactly as MTP-OFF output on
the deployed serving path.** "No detectable shift" is not an exactness result (Q2).

## Interim (Q8)

Exactness is the requirement and M3 / M4 are known defects → **the daily driver serves MTP-OFF until the fixes ship and
are re-certified** (registry `draft_kind` off for both picks in the daily overlay; all four client carriers checked per
AGENTS.md; operator go needed — it is a serving-config change). Bench runs: OFF (already the selection default).

## E — evidence (test-first in `../mlx-vlm`, production code path)

- **E1a mechanism, exact enumeration (Q1, Q2):** a genuinely HYBRID tiny qwen3_5 model (recurrent + full-attention
  layers, MTP head), tiny vocabulary and k; enumerate the exact joint law of the first-k emitted tokens ON vs OFF under
  the deployed sampling transforms (temperature, top_p, top_k, min_p from `main_models.yaml`) — must be equal up to float
  tolerance on every sequence. Drafters: (i) a compatible randomized drafter forced to LOW acceptance, (ii) a forced
  HIGH-acceptance drafter (worst case for M3 / M4), (iii) quantized tiny target + drafter fixtures (affine 4/8-bit as the
  picks use) so `quantized_verifier` / `exact_speculative_verify` branches run.
- **E1b paired-RNG identity:** position-keyed RNG so ON and OFF consume identical randomness per emitted position; with
  that, ON and OFF must emit bitwise-identical token sequences at T > 0 on the tiny fixtures — a direct test of the
  acceptance rule, no statistics.
- **E1c production conformance per pick (Q1, Q3):** for each deployed tuple (target revision, quant, drafter revision,
  KV mode, `mtp_verify_scan` policy — Fable `joint_v1`, uniform as registered), real weights and sidecars: shadow-compare
  verifier logits AFTER sampling transforms against singleton decode at the same positions, on prompts whose verifier
  blocks are forced to straddle each MLX key-length threshold (1,024 / 8,192 / 32,768 / 65,536), with serving policy and
  counters recorded. Under the exactness claim any output-relevant mismatch FAILS; "near tie" diagnoses, never excuses.
  If thresholds make bitwise equality impossible, the claim is renamed "bounded non-neutrality" with the measured bound
  and goes to the operator.
- **E2 greedy identity:** ON vs OFF token identity at T = 0 per pick on the frozen C84 set and long contexts (supporting).
- **E3 M4 on the deployed path (Q4, Q5):** two router HTTP turns with one forwarded session ID, backend
  `cached_session` asserted, history preserved; stop token placed at EVERY accepted-draft position; compare token IDs,
  KV, recurrent snapshots, drafter cache and next-turn output vs plain decoding. Continuous batching covered as a
  secondary path.
- **E4 M3 (Q6):** budget crossing at every block position, mismatch / full-accept / verifier-bonus cases; ON must emit
  plain decoding's exact forced sequence (`pop_forced_token_id`, e.g. newline then `</think>`) at the same position, and
  the next-turn state must match. Existing tests that bless block overshoot are replaced (MTP) or narrowed (suffix).
- **E5 M2 (Q7):** continuous batching with any logits processor selects plain `GenerationBatch` (zero speculative rounds
  asserted); **E5b:** cached requests with processors fall back and run zero draft rounds.
- **E6 M5 (Q7):** distinct seeds, changed admission / coalescing order, a late second row — seeded continuous-batch
  speculation falls back to plain or is refused.
- **E7 firing rates (Q8, supporting only):** counters for M3 and M4 events validated against scripted positives; replay
  of the C84 set + tg1 multi-turn sessions with session continuity, per pick; report events / opportunities with request-
  and accepted-block denominators and 95 % upper bounds (zero events → ≈ 3/n). Informs the incident record, not the
  interim decision.

## F — fixes in `../mlx-vlm` (minimal, fail-closed; Cursor code review)

- **M4 (Q5):** decide the emitted prefix (stop criteria wired into inline MTP) BEFORE drafter acceptance and target
  transaction commit; truncate `accepted` / `new_tokens` consistently; commit the shortened transaction (KV, recurrent,
  drafter cache, shared-KV positions, acceptance history) — singleton inline and batched loops.
- **M3 (Q6):** precompute plain decoding's emission decision before commit without double-advancing criteria; preserve the
  whole forced sequence; commit through the token preceding each forced output; handle the bonus-token case.
- **M2 / M5 (Q7):** fall back to plain decoding (or refuse) — no new state-carry machinery.

## G — gates (Q9, Q10)

- nvfp4 verifier failure (`test_general_quantized_verifier_matches_decode[127-nvfp4-4-16]`, pre-existing): repair, or a
  tracked format-specific xfail with proof that neither deployed artifact uses nvfp4; never reported as "green".
- Shared-loop regressions for other MTP drafter families in the fork's suite.
- Scope: suffix and non-MTP draft kinds are OUT of P369 and stay OFF / uncertified.

## R — release and re-certification (Q10)

Fork commit → Cursor code review cleared → fork push (operator go) → submodule bump (serving-path fingerprint recorded) →
full suites in both repos. Re-certify EACH pick separately on its current (model, drafter, quant, KV mode, verify policy,
cached-session backend), fresh OFF controls, every supporting quality axis, arm identity from manifests; C172 wash rule;
ship OFF if OFF wins beyond ±5 pp. Then the daily driver returns to ON and P368 layers 2–3 decide heavy runs. M63 rows stay
descriptive (predate the fix).

## Acceptance

E1a equal laws; E1b bitwise identity; E1c no output-relevant mismatch per pick (or an operator decision on a bounded
claim); E3–E6 red before / green after; E7 reported; G gates met; Cursor cleared on the fork diff.

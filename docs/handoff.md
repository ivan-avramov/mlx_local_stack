# Handoff — 2026-10-04 (late): M57 attention design reviewed twice under the performance-maximizing lens; NOTHING approved, built or run

THE one handoff (AGENTS.md: rewritten in place each session). Read this, then `docs/proposal-flash-attention.md` (the whole M57 record:
GPT-Astra proposal → review 1 → design session P25–P44 → review 2 (Claude) → review 3 (Codex) → reconciliation), then `docs/PLAN.md` <!-- allow-shorthand -->
(the only queue; M57 is NOT in it yet) and `docs/open-questions.md`. Results: `docs/campaign-results.md` 2026-10-04 (M55).

## State of the world

- **Git:** pushed through `bd2823d`; later commits are local only (handoff/stack-down note, this session's docs). Push needs the operator's word.
- **Stack is DOWN by operator instruction (2026-10-04): do NOT auto-start `runserver.sh`.** Verified this session: :8000 free, no router /
  worker processes. Power gate read 140 W / 28 V, battery 96 %.
- **This session was design + review only.** No GPU work, no model load, no fork or harness change. Workdir: `$STACK_WORKDIR/m57/`
  (Codex brief, log and raw review).
- **Picks unchanged.** M55 landed (previous handoff); M56 parked (C110 wait-and-watch).
- `ts.md` at the repo root is the operator's untracked video transcript (HySparse2 / DeepSeek V4.1-Flash) — not committed.

## M57 — where the design stands

Operator's lens for this track (2026-10-04): maximise the performance potential (prefill, decode, memory) without sacrificing output
quality beyond a negligible amount; implementation time is not a constraint; new kernels or a sparse retrofit are acceptable if they
are believed to lead to a better outcome.

Source-verified facts that changed the design (MLX 0.32.2 dispatch source; full text in review 2):

- Single-token decode and MTP verification (drafter block 3) are ALREADY on MLX's fused vector kernel under `auto`; a flag changes only
  query lengths > 8.
- A blanket `force_fused` raises for query lengths 6–8 at this model's GQA factor 6 — routine for chunk tails and short turns. The
  policy must be shape-aware in the fork.
- The checkpoint is bf16; the only microbench so far was fp16.
- Upstream's `auto` rule for head dim 256 ignores key length (unchanged in 0.32.3 and main).
- The existing ladder peaks fit "one 512-row score tensor + whole-prompt embeddings" to 98.5 % of the slope: ≈ 6.4 GB of the 47.1 GB
  256K peak is unfused score scratch, ≈ 2.7 GB is embeddings. Prediction, not yet measured on the serving path.

- MTP verification is a SECOND attention site (`qwen3_5/speculative_verifier.py`, found by Codex, re-checked): length 2 jointly,
  longer blocks as separate single-query calls — up to three full key/value scans per round with block 3. That, not a slow kernel,
  explains the long-context decode drop (44 → 13 tok/s at 261K); the decode lever is a joint verification scan.

Both reviews agree on direction (no blanket force; versioned shape-aware policy; chunk size co-designed; evidence before build; sparse
retrofits probe-gated, decode before prefill). Consolidated recommendation (P63 in the proposal doc):

1. Evidence before any build: CPU transcript / cache-event accounting of M54/M55 (new, tool-output and reprocessed tokens, context
   size, cold replays); ≈ 1 box-hour of no-model GPU microbenchmarks (bf16 crossover / raise / parity matrix with a validated memory
   instrument; vector-kernel scan time against a read floor, `MLX_SDPA_BLOCKS`); one overlay probe at 128K with
   `prefill_step_size: 1024` under `auto` (TTFT and peak).
2. An env-gated component profiler in the fork (attention / GatedDeltaNet / MLP / verifier time on the served path).
3. M57 = versioned shape-aware dispatch policy over ALL native call sites (attention module, verifier, tails, snapshot cuts) + chunk
   size chosen jointly + policy-aware pool limit + lazy per-chunk embeddings + fingerprint v7; qualified once on the winning recipe
   with the corrected, stratified quality design (Codex X14–X16).
4. Next milestone candidate: long-context decode — joint verification scan, MTP-ON requalified (estimate 13 → ≈ 25 tok/s at 261K).
5. Then, each behind its measurement: GatedDeltaNet / MLP prefill work, upstream report + pinned-commit kernel comparison, fused
   low-precision cache, sparse decode, sparse prefill last.

Predictions on record (to be falsified): TTFT 64K 111 → 76 s, 128K 325 → 185 s, 256K 1063 → 500 s; 256K peak 47.1 → ≈ 40.7 GB
(≈ 38 GB with lazy embeddings).

## Pending (operator)

1. Decide the M57 scope after reading the two reviews. Three rulings needed: (a) run the step-1 evidence (≈ 1 box-hour GPU, no model
   load, + CPU); (b) fund the env-gated component profiler in the fork; (c) accept M57 as scoped in P63 item 3 instead of the
   `auto | force_fused` flag.
2. Open design decisions carried from the design session: long-context quality subset in the qualification; Q2 thresholds; whether to
   record P41 (watch-list for an open HySparse2-class checkpoint) and P42 (harder long-context benchmarks) in `docs/open-questions.md`.
3. Nothing is queued in `docs/PLAN.md` for M57 until (1) is ruled. On approval: PLAN row, `docs/specs/m57-attention-policy.md`,
   C111 in `docs/open-questions.md`, then the M54 funnel (Sonnet implementer, cold reviews Claude + Codex `gpt-6-astra`, live gate,
   pilot twice).
4. M56 LiveCodeBench window: PARKED (C110) — re-check on each release for a window starting after 2026-06.

## Rules learned this session

- Read the dispatch source before designing around a kernel flag: three claims in the first design (MTP verification unfused, raise
  conditions, contiguity copies) were wrong and one hazard (query lengths 6–8) was invisible without it.
- A memory instrument that has not shown the known positive cannot report a zero (the microbench's "no memory benefit").
- Codex cold design review: `codex exec -m gpt-6-astra -s read-only -o <file>`; give it the design record and the lens, not conclusions.

Next decision id C111; discussion ids continue from P60.

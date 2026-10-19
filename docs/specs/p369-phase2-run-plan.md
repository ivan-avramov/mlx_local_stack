# P369 phase 2 — GPU worker-conformance run plan (E1c, E2, E7) — PLAN v2, 2026-10-18

Status: v2 → Cursor plan review round 2. v1 → round 1 `DISAGREE Q15–Q27`
(`docs/reviews/p369-phase2-plan-round1.cursor-gpt-5.6-sol-high.md`), all accepted and applied here. Parent:
`docs/specs/p369-mtp-certification.md` (v3) §E1c, §E2, §E7. GPU go: C175 (this phase only). Operator choices: C182 (in-process
worker harness, reconstructed C84 items, full variant); the round-1 changes to time (Q25) and P387 (Q26) go back to the operator.
**Production source pinned: fork `p369-mtp` `4e6d0e03`** (code review cleared, round 8). Harness and P387 commits are test /
dev only; the run refuses unless `git diff 4e6d0e03 -- mlx_vlm ':!mlx_vlm/tests'` is empty (Q27). No serving-configuration
change: the daily driver stays MTP-OFF (C177); no router runs. Claims made here are WORKER conformance (the fork's real CLI,
app, endpoint, templating, cached-session path); router claims belong to the per-pick re-certification on real chains (Q20).

## 1. What this phase decides

- E1c (acceptance): per pick, on real weights at the deployed tuple, MTP-ON's emitted-position target distributions AFTER the
  sampling transforms, and its committed target state, equal plain singleton decoding at the same positions — else the claim
  becomes "bounded non-neutrality" with the measured bound (support changes, worst per-token probability delta, TV distance)
  and goes to the operator.
- E2 (supporting): greedy ON vs OFF identity of the first 512 tokens per pick, incl. long-context regimes.
- E7 (supporting, incident record only): how often the PRE-FIX M3 / M4 conditions occur on real traffic.

## 2. Harness (built first: test-first, Cursor code review, full fork suite twice, eight audits — before any GPU minute)

Fork-only, test-only code (`dev/p369_phase2/`, CPU tests in `mlx_vlm/tests/test_p369_phase2_harness.py`).

### 2.1 Worker fidelity (Q20)

- Each (pick, arm) runs in its own subprocess with a SANITIZED environment (only the variables the router would pass +
  `MLX_VLM_CACHE_SESSION_MAX=1`; every `MLX_VLM_*` / `KV_*` / draft variable cleared first, since `cli.main` writes draft
  model / kind only conditionally).
- Worker argv from mlx-serve's own config loader + `process_manager._build_command(model_cfg)` on a harness-local overlay of
  `main_models.yaml` that restores exactly the three C177 lines for the pick; OFF = the same overlay minus them (= today's
  registry). The argv runs through the fork's `mlx_vlm.server.cli.main`; `uvicorn.run` is intercepted and the
  `"mlx_vlm.server:app"` string resolved AFTER the CLI setup; requests go through `TestClient(app)` (lifespan preload) with
  `X-MLX-VLM-Chat-Id`.
- Asserted per process: every imported `mlx_vlm` module resolves under the reviewed worktree; backend `cached_session` on
  every request; APC disabled; ON has the drafter loaded and positive MTP rounds on EVERY request; OFF has no drafter loaded
  and zero draft rounds; the verify policy (`joint_v1` / `per_query`) observed on the instance.

### 2.2 E1c observation and replay (Q15–Q19)

- **Rows (Q15):** the ON wrapper persists per round `emitted_before`, cache offset, `verify_input`, `accepted`, `n_emit`, the
  terminal index and every verifier logit row. Compared rows = every EMITTED target row: the accepted drafts' rows, plus the
  first rejection's replacement row, or the bonus row when all drafts accept. Only rows after the first rejection (unreachable
  history) are excluded. Position 0 (the prefill's first token) is compared separately from the prefill logits on both sides.
- **Reference (Q17):** a sequential clean replay in a fresh subprocess through the OFF arm's `stream_generate` with a
  recording + forcing logits processor injected ONLY there: it records the raw logits BEFORE modifying them, then forces the
  ON-emitted token, so the replay walks the identical history one token at a time. OFF asserts no drafter, ON positive rounds.
- **Comparator (Q17):** both sides through `_PositionedTargetSampler._filter` + temperature with the pick's deployed values,
  then canonicalised to probabilities (log-sum-exp normalised, so an additive constant cannot false-fail); PASS needs
  bit-equal support and values. On any mismatch: support changes, worst per-token probability delta, total-variation
  distance, near-tie margins (diagnostic only).
- **State (Q16):** at prompt end and at EVERY target commit (block commits and width-one `_mtp_commit_pending_token`
  commits), at the same logical offsets in the replay: per cache leaf the offset, shape and dtype, the valid K / V (incl.
  TurboQuant scales / biases / metadata), every recurrent / GatedDeltaNet state component, and the full next-token logit
  vector of a fixed probe token (id recorded) through a transactional verify-forward followed by `abort()`. Never the
  preallocated tails. Cost control: per commit an exact GPU digest (two independent multiply-accumulate digests over the
  bit-cast bytes, mod 2^32, over the newly written K / V slots and every recurrent component); the full valid prefix by
  sha256 at prompt end, at each threshold crossing and at request end. A digest mismatch is a FAIL.
- **Kernels (Q18):** before any GPU minute, a CPU inventory from each pick's weights lists every linear the verifier calls
  with its type (quantized bits / group size, or dense) and which `speculative.ops.linear` alias it reaches; spies sit on
  those aliases (`_target_verify_quantized_linear`, `_target_verify_quantized_argmax`, `_target_verify_weight`, the
  singleton / timewise fallbacks). PASS needs, per ON request, hits on every kernel family the inventory says is reachable,
  and zero hits on a fallback the inventory says is not used. If the dense `exact_speculative_verify` kernel is unreachable
  on both real tuples (all text linears quantized), its coverage stays phase-1 fixture evidence (the parent's Q14 named the
  tiny fixtures) and the report says so; E1c then certifies the quantized verifier only.
- **Straddles (Q19):** the prompt's FINAL post-template token count is constructed and asserted to be T − 64 for
  T ∈ {1,024; 8,192; 32,768; 65,536}; the observer captures every verifier call's actual key lengths and planner
  classification. Fable: per-request `verify_blocks_straddle` delta > 0 at each T and an empty `verify_fallback_reasons`;
  uniform: observed per-query TurboQuant verifier calls with key lengths on both sides of every T. A request that terminates
  before covering its threshold is INVALID (never a pass); the next seed from a pre-registered list of 5 is used; five
  invalid seeds fail that cell.

### 2.3 E7 classes, reconstructed against the pre-fix code (Q23)

Pre-fix behaviour = `0b43dae4^` (the parent of the first M3 / M4 fix commit). A wrapper around the round loop records per
round the accepted drafts, the bonus, the stop / budget / forced decision and its index; a hook in the caller records the
prefill's first token. Classes:
- **M4a** — a stop token among the ACCEPTED drafts with ≥ 1 later accepted draft (pre-fix: those drafts were committed).
- **M4b** — terminal on the prefill's first token, or on the verifier bonus / a pending replacement (pre-fix: the terminal
  token stayed out of the cache and the next turn diverged).
- **M3** — the thinking-budget criterion requests a forced token at index i of a block with ≥ 1 token after i emitted
  pre-fix; recorded with the trigger index and the pre-fix overshoot count.
Each predicate has a scripted positive (and a near-miss negative) on the tiny hybrid fixture, run both live (current code)
and against the `0b43dae4^` behaviour.

### 2.4 Operations (Q25)

Exclusive run lock (`$STACK_WORKDIR/p369/phase2/.lock`); refusal unless ports 8000 (router) and 8091 (worker) are free and
no `mlx_vlm.server` / `mlx-serve` / `mlx_vlm` / `pytest` / `opencode` / bench process runs (full command lines inspected, own
pid excluded); free disk ≥ 20 GB; `pmset -g ac` 140 W / 28 V, battery > 20 %, thermal state logged. Per-request watchdog
(derived from max tokens / floor decode rate + headroom) and a total-wall watchdog; a timeout or censored request can never
pass and is reported. Atomic result / exit-status files; post-lifespan check that the model and the GPU thread are released
before the next subprocess. Detached launch, background waiter, daemon log every 5 min (phase / item, ETA vs estimate,
errors, mismatch / event counts, power, thermal).

## 3. Runs (per pick: Fable first, then uniform)

Tuples: **Fable** — native16 KV (`kv_bits: 0`), `joint_v1`, prefill 512, `fused_v1`, lazy embeddings, prealloc 262,144,
shrink on, drafter `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter`; **uniform** — TurboQuant 4-bit KV,
`per_query`, prefill 512, prealloc 262,144, drafter `caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter`. Weight revisions + file
sha256 recorded before load.

- **Smoke (≈ 10 min):** Fable E1c at T = 1,024 + E2 on 2 items, both arms; the comparator's injected positives (a 1-ulp
  logit change at one emitted row, a flipped K byte at one commit, a changed GDN element, a changed probe logit) must each
  fire on the live data; kernel spies non-zero.
- **E1c:** 4 straddle prompts + 1 short chat prompt; deployed sampling, fixed seed list; 160 generated tokens. Criteria §2.2.
  On FAIL: finish that pick's E1c (to measure the bound), skip its E2 / E7, report.
- **E2 (Q21, Q22):** the **C84-item reconstruction** (not the frozen C84 set — its raw requests are not on this box): the
  five ids per axis in `benchmark/results/<pick>/{math500,humanevalplus,mbppplus,cjudge}.c84bundle-after-<kv>-20260914.jsonl`
  (`<kv>` = `native16` for Fable, `tq4` for uniform), rebuilt by the stack bench's prompt builders at a pinned commit and
  dataset revisions; the reconstructed token ids are recorded (sha256) and their count must equal the row's `prompt_tokens`;
  a failed reconstruction FAILS coverage (never silently dropped). Temperature 0, `max_tokens` 512; plus straddle prompts at
  1,024 / 8,192 / 32,768 / 65,536 (160 tokens). Arms: OFF, ON, OFF again (reload control) on the 20 items; OFF and ON on the
  straddles. Spies on `speculative_argmax_from_hidden` and the quantized-argmax alias, positive verifier rounds on every ON
  request. PASS: first-512-token (straddles: 160) identity ON == OFF on every request, given an identical control; a
  differing control makes E2 informative only.
- **E7a (Q24):** the 20 reconstructed items per pick at deployed sampling with recorded seeds, MTP ON, full deployed budgets,
  cached-session path. **E7b:** two stored tg1 / M63 opencode sessions per pick replayed with TRUE continuity: each request
  appends the model's own previous assistant turn (and the recorded tool results / user turns that follow it), one chat id;
  cached-token reuse must be > 0 after turn one, else the session is labelled teacher-forced exposure; time-boxed 10 min per
  pick, unfinished sessions reported as censored. Statistics: per class, requests-with-event / requests with a
  Clopper–Pearson 95 % interval (zero events → ≈ 3/n); class-eligible block rates descriptive only. Censored requests do not
  count as event-free.

## 4. Estimate (Q25)

E1c ≈ 215K prefill tokens + ≈ 1.6K decode / replay steps per pick (+ per-commit digests and probe forwards); E2 three arms ×
20 items × 512 tokens + two arms × ≈ 107K straddle prefill per pick; E7a ≈ 11–14 min per pick from C84 history with a
heavy-tail allowance (one 102,400-token runaway ≈ 1–2 h — bounded by the per-request watchdog, reported as censored).
Reserve **2.5–3 h of GPU time** plus harness build, review and suites (≈ half a session). The handoff's "≈ 1 h" and v1's
"≈ 100 min" were optimistic.

## 5. P387 (fork tests vs the C177 registry), revised by Q26

Measured: against the live MTP-OFF registry the P369 tests give 56 failed + 9 errors + 1 collection error (the worktree hides
it: no sibling ⇒ pinned fixture). Revised fix (test-only, red first, before the fork push): ordinary tests are DETERMINISTIC —
both the certified MTP tuple and the sampling come from the pinned golden fixture, and the presence of a sibling checkout no
longer changes the normal suite. A separate opt-in live-registry test (`MLX_REQUIRE_STACK_REGISTRY=1`) compares the live
registry with the fixture field by field and accepts exactly two states: identical, or the C177 interim (only `draft_kind`,
`draft_model` and Fable's `mtp_verify_scan` absent, each with the `P369 INTERIM (C177` marker). C182 approved the v1 variant
(sampling from the live registry); this change goes back to the operator.

## 6. After this phase

Results → `docs/open-questions.md` P369 + handoff. Then fork push (operator) → submodule bump (full suites in both repos) →
per-pick re-certification ON vs OFF on real router chains (own plan, Cursor review, operator GPU go) → restore MTP-ON (C177
lines + `test_opencode_probe_seeding.py` expectation) → P368 layers 2–3.

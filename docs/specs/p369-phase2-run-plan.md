# P369 phase 2 — GPU worker-conformance run plan (E1c, E2, E7) — PLAN v13, 2026-10-20

**v13 = v12 after Cursor plan round 3 of 3 (DISAGREE V14 V15; V16 V17 also applied; V8–V13 resolved incl. the contested V9 —
`docs/reviews/p369-v10/plan-round3.*`) — escalated to the operator, lead rec: accept v13 without a fourth round.**

**v12 = v11 after Cursor plan round 2 of 3 (DISAGREE V9 V10 V11; V8 V12 V13 also applied; V9 partly contested with the C188
carry-over rule — `docs/reviews/p369-v10/plan-round2.*`).**

**v11 (2026-10-20) = v10 after Cursor plan round 1 of 3 (DISAGREE V1 V2 V3 V5 V6 V7; all seven findings accepted —
`docs/reviews/p369-v10/plan-round1.*`).** v10 (C191, operator: "the goal here must be to qualify and enable MTP across the
picks") = v9 + §3.1: the phase covers EVERY MTP-certified registry entry — `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` and
`Ornith-1.0-35B-mlx-uniform-4bit` join the two Qwen3.8-27B picks; §5 accepts the P406 interim registry state.
**Pins (v11, V1):** PRODUCTION-code pin = fork `7207179b` (P400 + P401 + P405 F1 / F2 / K6; the run refuses unless
`git diff 7207179b -- mlx_vlm ':!mlx_vlm/tests'` is empty) — this supersedes every earlier production pin named below
(`4e6d0e03`, `da27f0ef`), which describe completed runs only; the HARNESS / reviewed head is bound separately
(`--reviewed-head`, the Cursor-cleared descendant of `6911b17f`); both hashes are recorded in every manifest.

Status: **v9 = v8 + §2.2 forced positions (P398, found by GPU smoke 3)**; v8 = v7 + §3 E2 on the same-instance design (C185 / P393); reviewed with its build (code review round 1 of 3, C186). v7 — Cursor round 7 `VERDICT: AGREE` (`docs/reviews/p369-phase2-plan-round7.cursor-gpt-5.6-sol-high.md`); the harness is built → its code review. v6 → round 6 `DISAGREE Q35 Q38` (incomplete closures; Q36 Q37 Q39 Q40 closed;
`docs/reviews/p369-phase2-plan-round6.cursor-gpt-5.6-sol-high.md`), both applied in v7. v5 (= v4 + §2.5, P391) → round 5 `DISAGREE Q35–Q40`, all applied here
(`docs/reviews/p369-phase2-plan-round5.cursor-gpt-5.6-sol-high.md`). **v4 — Cursor round 4 `VERDICT: AGREE`** (`docs/reviews/p369-phase2-plan-round4.cursor-gpt-5.6-sol-high.md`) → build the harness;
the operator items (2.5–3.5 h budget, the E7b narrowing, P387 per Q26) are pending in the handoff. v3 → round 3 `DISAGREE Q29 Q34` (all else closed; both applied here;
`docs/reviews/p369-phase2-plan-round3.cursor-gpt-5.6-sol-high.md`). v2 → round 2 `DISAGREE` (closed Q15 Q17 Q19–Q21 Q25–Q27; open Q16 Q18 Q22–Q24 via
new Q28–Q33, all accepted and applied here; `docs/reviews/p369-phase2-plan-round2.cursor-gpt-5.6-sol-high.md`). v1 → round 1
`DISAGREE Q15–Q27` (`docs/reviews/p369-phase2-plan-round1.cursor-gpt-5.6-sol-high.md`), all accepted. Parent:
`docs/specs/p369-mtp-certification.md` (v3) §E1c, §E2, §E7. GPU go: C175 (this phase only). Operator choices: C182 (in-process
worker harness, reconstructed C84 items, full variant); the round-1 changes to time (Q25) and P387 (Q26) go back to the operator.
*(Historical, V8: the completed `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` full run used production pin `4e6d0e03`; smokes
9–11 used `da27f0ef`. The ONLY production pin for v10+ runs is `7207179b`, stated above.)* No serving-configuration
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
  every request; APC disabled; the verify policy (`joint_v1` / `per_query`) observed on the instance. Per TRAJECTORY
  (v6, Q39): an ON request has the drafter attached and positive MTP rounds; a detached replay in the ON process and
  every request of an OFF-arm process have zero draft rounds (an OFF-arm process has no drafter loaded).

### 2.2 E1c observation and replay (Q15–Q19)

- **Rows (Q15):** the ON wrapper persists per round `emitted_before`, cache offset, `verify_input`, `accepted`, `n_emit`, the
  terminal index and every verifier logit row. Compared rows = every EMITTED target row: the accepted drafts' rows, plus the
  first rejection's replacement row, or the bonus row when all drafts accept. Only rows after the first rejection (unreachable
  history) are excluded. Position 0 (the prefill's first token) is compared separately from the prefill logits on both sides.
  **v9 (P398):** a verifier block's rows past its emission cut (rejection, stop, length budget or a thinking-budget
  forced token) are unreachable history and dropped at the cut; forced tokens are emitted with no sampler call, so the
  ON positions without a row must be EXACTLY the forced emissions (tokens equal the forced sequence in order; else a
  harness error) and are excluded from the ON/OFF1 row comparison and reported; states are compared at every commit and
  C1 / C2 compare every position. E1c's row claim covers every SAMPLED emitted position.
- **Reference (Q17; v6 §2.5):** a sequential clean replay of the forced ON tokens one token at a time — the verdict's
  reference is the SAME-INSTANCE detached replay (OFF1, §2.5), the cross-load OFF arm is comparison C2. Observation point
  (build note): the production sampler (`_PositionedTargetSampler.sample_target`) records the rows it is handed and,
  in a replay, returns the forced token — no logits processor is installed, so the plain path is unchanged.
- **Comparator (Q17):** both sides through `_PositionedTargetSampler._filter` + temperature with the pick's deployed values,
  then canonicalised to probabilities (log-sum-exp normalised, so an additive constant cannot false-fail); PASS needs
  bit-equal support and values. On any mismatch: support changes, worst per-token probability delta, total-variation
  distance, near-tie margins (diagnostic only).
- **State (Q16, Q28):** at prompt end and at EVERY target commit (block commits and width-one
  `_mtp_commit_pending_token` commits), at the same logical offsets in the replay, ONE SHA-256 over a canonical byte stream of
  the COMPLETE logical valid state: per cache leaf (in layer order) its type, offset, valid length, shapes and dtypes, every
  valid packed / native K / V component (TurboQuant codes, scales, biases and codec metadata included) and every recurrent /
  GatedDeltaNet component (conv + SSM state); hashed in bounded chunks after `mx.eval`; preallocated tails never included.
  Then the full next-token logit vector of a fixed probe token (id recorded) through a transactional verify-forward
  followed by `abort()`, compared bitwise; each probe is proven observationally neutral by an equal state hash before and
  after it. Any hash or probe-logit mismatch is a FAIL. Size: Fable native16 KV is 64 KB per token over its 16 attention
  layers (≈ 4.3 GB valid at 65,536), the 48 GDN layers ≈ 150 MB; uniform TQ4 ≈ ¼ of the KV. Cost is calibrated at 65,536 in the
  smoke (§3) and the wall estimate revised before the full run.
- **Kernels (Q18, Q29):** a CPU manifest from each pick's weights lists every linear the verifier can call with its type
  (quantized bits / group size, or dense) = the EXPECTED eligibility only. Runtime outcome telemetry is authoritative:
  instrumented are every consuming alias (incl. the by-value imports in `models/qwen3_5/speculative_verifier.py`:
  `_target_verify_linear`, `_target_verify_linears`, `_target_verify_embedding_as_linear`, `_target_verify_quantized_linear`,
  `_target_verify_quantized_argmax`) AND the nested implementations they dispatch among (optimized affine, NVFP4, singleton
  quantized, timewise / singleton fallbacks, `_target_verify_weight`, plain `linear(x)`, and — inside
  `_target_verify_linears` — the fused `_decode_quantized_linears_fused` branch (`mx.quantized_matmul`) classified apart from
  that function's per-linear tuple fallback, Q29); a family counts only when it
  returned a non-`None` result; every projection call is classified exactly once with module, shape and dtype. PASS needs,
  per ON request, positive verifier (and, at T = 0, argmax) calls, the expected successful families, and zero unclassified or
  forbidden fallback calls. The full campaign is gated on the smoke's runtime inventory reconciling with the static
  manifest. If the dense `exact_speculative_verify` kernel is unreachable on both real tuples, its coverage stays phase-1
  fixture evidence (the parent's Q14 named the tiny fixtures) and the report says so.
- **Straddles (Q19):** the prompt's FINAL post-template token count is constructed and asserted to be T − 64 for
  T ∈ {1,024; 8,192; 32,768; 65,536}; the observer captures every verifier call's actual key lengths and planner
  classification. Fable: per-request `verify_blocks_straddle` delta > 0 at each T and an empty `verify_fallback_reasons`;
  uniform: observed per-query TurboQuant verifier calls with key lengths on both sides of every T. A request that terminates
  before covering its threshold is INVALID (never a pass); the next seed from a pre-registered list of 5 is used; five
  invalid seeds fail that cell.

### 2.5 Same-instance pairing and the two controls (P391, v5; round 5 applied in v6)

`docs/metrics.md` (Seeds, scope correction) measured that byte-identity holds only within ONE loaded-model lifetime:
after an unload + reload, seeded rows differed on 55 / 142 AgentBench tasks (mechanism open). So:

- **E1c claim and verdict (Q36):** "MTP-ON equals PLAIN decoding on the same MTP-loaded target instance". In the ON
  worker, per cell: the ON request; then, with the drafter detached (`ResponseGenerator.draft_model` / `draft_kind` =
  `None`; the cached path reads both per request via `_inline_draft_kwargs`), the forced OFF1 replay and the forced
  OFF2 replay. ON vs OFF1 = the verdict (§2.2 criteria).
- **Trajectory isolation (Q35):** ON, OFF1 and OFF2 share the target model and its verify-policy objects (asserted
  unchanged) but each runs a fresh chat id on a fresh, initially empty cache tree (no reused prefix:
  `cached_tokens == 0`, asserted). Release (v7, round 6): after each trajectory the harness clears that chat's
  `PromptCacheState`, removes the session entry, drops its recorder's cache reference and proves with weak references
  (after `gc.collect()`) that every leaf cache of the tree was collected — BEFORE the next trajectory starts (eviction by
  `MLX_VLM_CACHE_SESSION_MAX=1` alone only drops the dict entry). Identity-disjointness follows (an `id()` comparison
  would be unsound once objects are freed). The smoke positives run on OFF1's live cache before OFF1 is retired.
- **Detachment window (Q38):** set only after the ON request's `_process_cached_request` has RETURNED (a
  harness-observed exit acknowledgement on the GPU thread, counted in a wrapper's `finally`) and the worker is idle
  (request queue empty, `in_flight == 0`); held through both replays — each again waits for its exit acknowledgement
  and idleness — and restored in `finally`; no concurrent ingress (one
  harness thread). During it, a guard asserts `_inline_draft_kwargs` returned `{}`, no speculative-prefill capture was
  requested, zero verify-scope projection calls and zero draft rounds; the transactional probes are tagged apart.
- **Control C1 (within instance, Q37):** OFF1 vs OFF2 — raw rows, transformed distributions, the emitted token
  sequence = the forced tokens for both, ON's finish reason, the complete expected offsets / requests, state hashes at
  every offset, probe logits. Any difference or incompleteness (early stop, timeout, missing offset, a token not
  emitted) fails C1.
- **Comparison C2 (cross-load / configuration, Q36):** the OFF arm in its own subprocess (the deployed OFF argv: no
  drafter loaded, no Fable verify-policy stamping, a different process and allocator history) replays the same
  forced tokens and is compared with OFF1. Reported per cell as `identical` or `unestablished`; a difference is
  CONSISTENT WITH reload nondeterminism (P391) but does not identify a mechanism; a match is evidence for the sampled
  cells only. It never decides E1c.
- **Precedence per pick (Q37):** (1) C1 fails or is incomplete on any cell → ABORT that pick: no E1c verdict, no
  measured bound, its E2 / E7 skipped; (2) C1 passes and the ON / OFF1 pair differs on any cell → FAIL: that pick's
  remaining E1c cells finish (for the bound), its E2 / E7 skipped; (3) all pairs pass → E1c PASS (the claim above),
  `cross_load: identical | unestablished` from C2.

### 2.3 E7 classes, reconstructed against the pre-fix code (Q23)

Pre-fix behaviour = `0b43dae4^` (the parent of the first M3 / M4 fix commit). A wrapper around the round loop records per
round the accepted drafts, the bonus, the stop / budget / forced decision and its index; a hook in the caller records the
prefill's first token. Classes:
- **M4a** — a stop token among the ACCEPTED drafts with ≥ 1 later accepted draft (pre-fix: those drafts were committed).
- **M4b** — terminal on the prefill's first token, or on the verifier bonus / a pending replacement (pre-fix: the terminal
  token stayed out of the cache and the next turn diverged).
- **M3** — the thinking-budget criterion requests a forced token at index i of a block with ≥ 1 token after i emitted
  pre-fix; recorded with the trigger index and the pre-fix overshoot count.
Oracle (Q30): the classes are validated by a self-contained external regression test that runs the same scripted cases
on the tiny hybrid fixture in two isolated checkouts — `88724023` (= `0b43dae4^`, pre-fix) and `0b43dae4` (the fix) — each in
a fresh interpreter with only that tree on `sys.path`; each case must show its precise old defect (M4a: committed past the
stop; M4b: the terminal token missing from the cache and the next turn diverging; M3: the overshoot count) pre-fix and the
fixed outcome post-fix, plus a near-miss negative. The live wrappers on the current code only OBSERVE events; they are never
the oracle. M4b's hooks cover `speculative/utils.py` and the generation consumer, not only `_mtp_rounds`.

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

- **Smoke (≈ 30 min):** Fable E1c at T = 1,024 and at T = 65,536 (hashing / probe cost calibration) with the full §2.5
  structure (ON, OFF1, OFF2 in the ON process; the cross-load OFF arm), + E2 on 2 items (v8: the same-instance triple in the ON process + the cross-load OFF process). Injected positives on the live data (Q32): a 1-ulp raw-logit change detected AT THE RAW RECORDER; a precomputed
  in-support perturbation guaranteed to change a retained transformed probability (or the support boundary) detected by
  the comparator; a flipped K byte in an OLD prefix position, a changed TurboQuant scale (uniform smoke), a changed GDN
  element and a changed probe logit each detected by the state check. The runtime kernel inventory must reconcile with the
  static manifest (Q29). Uniform gets the same smoke before its full run.
- **E1c:** 4 straddle prompts + 1 short chat prompt; deployed sampling, fixed seed list; 160 generated tokens. Criteria §2.2.
  On FAIL: finish that pick's E1c (to measure the bound), skip its E2 / E7, report.
- **E2 (Q21, Q22; v8 same-instance design, C185 / P393):** items = the **C84-item reconstruction** (not the frozen C84 set — its
  raw requests are not on this box): the five ids per axis in
  `benchmark/results/<pick>/{math500,humanevalplus,mbppplus,cjudge}.c84bundle-after-<kv>-20260914.jsonl` (`<kv>` = `native16` for
  Fable, `tq4` for uniform), rebuilt by the stack bench's prompt builders at a pinned commit and dataset revisions; the
  reconstructed token ids are recorded (sha256) and their count must equal the row's `prompt_tokens`; a failed reconstruction
  FAILS coverage (never silently dropped). Temperature 0, `max_tokens` 512; plus (full run only) straddle prompts at 1,024 /
  8,192 / 32,768 / 65,536 (160 tokens).
  - **Same-instance triple (the verdict's instrument).** In the ON worker (worker mode `e2_pair`), per request: greedy **ON**
    (drafter attached); then, after its `_process_cached_request` exit acknowledgement and worker idleness (`wait_idle`), with
    the drafter detached (`drafter_detached`) and under `DetachedGuard`, greedy **OFF1** and greedy **OFF2** on the same loaded
    target. Each trajectory uses a fresh chat id; every one must report `cached_tokens == 0` (no reused prefix); after each,
    its session entry is released (`release_session`) before the next starts. The target model and verify-policy objects are
    asserted unchanged across the triple (as in E1c). OFF1 and OFF2 must run zero MTP rounds and zero verify-scope projection
    calls, and the guard must record no draft kwargs / speculative-prefill capture; a violation is a harness error.
  - **Engagement (ON):** positive `speculative_argmax_from_hidden` calls (the T = 0 argmax readout), a passing kernel verdict
    and positive MTP rounds on every ON request; every trajectory's templated prompt digest equals the reconstruction's (C84
    items) and the three trajectories' digests are equal.
  - **Control C1-E2 (within instance):** OFF1 vs OFF2 — identical token ids and finish reason on every request.
  - **Verdict per pick (precedence):** (1) C1-E2 differs on any request → **ABORT** (within-instance nondeterminism: the
    instrument cannot decide; reported, never an MTP finding); (2) any ON request not engaged or any digest problem →
    **INCOMPLETE**; (3) ON vs OFF1 token ids (first 512; straddles 160) differ on any request → **FAIL**; (4) else **PASS** —
    the claim reads "greedy MTP-ON equals plain greedy decoding on the same MTP-loaded instance". Every evidence flag is an
    exact boolean (C186 H34). E2 never skips E7: E7 is an independent incidence record.
  - **Cross-load comparison (reported, never decides; like C2):** the separate OFF-arm process (the deployed OFF argv) runs
    the same greedy requests once; per request `identical` or `unestablished` vs OFF1, summarised as `cross_load`. A
    difference is consistent with reload nondeterminism (P391), identifies no mechanism and never changes the E2 verdict.
    v7's second OFF process (the reload control) is dropped: the same-instance triple removes the confound it detected.
  - Smoke: the 2 first reconstructed items (triple + cross-load OFF); the smoke gate needs E2 PASS. A supervisor stop
    (`JobTimeout`) makes E2 INCOMPLETE.
- **E7a (Q24):** the 20 reconstructed items per pick at deployed sampling with recorded seeds, MTP ON, full deployed budgets,
  cached-session path; independent requests ⇒ per class requests-with-event / requests with a Clopper–Pearson 95 % interval
  (zero events → ≈ 3/n); class-eligible block rates descriptive only; censored requests never count as event-free.
- **E7b (Q31, Q33) — narrowed, operator to confirm:** stored opencode sessions cannot be continued faithfully without
  executing the model's own (different) tool calls, so E7b is SCRIPTED multi-turn chat continuity without tools: 5 of the
  reconstructed items per pick, each followed by two fixed user follow-ups; every request appends the model's own previous
  assistant turn; one chat id; the cached-token count must reach the token boundary through the previous generated assistant
  turn (asserted against the session's recorded hash chain), else the session is censored. Reported descriptively per
  session, never pooled with E7a. Tool-session exposure is NOT measured here (parent §E7 named tg1 sessions); it would need
  production MTP event counters in the worker (a fork change of its own) and is recorded as a gap.

### 3.1 v10 / v11 — the two further MTP-certified entries (C191)

Both are MTP-ON certified (M6b / M27) and were served MTP-ON on the pre-fix fork until C191 (P406).

- **Campaigns (v11 V2, v12 V9 / V13):** exactly FOUR pre-registered, independently authorized campaigns on production pin
  `7207179b`, in order: (1) `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` — a REGRESSION SMOKE only, under the operator-approved
  C188 carry-over rule (its full-run PASS on `4e6d0e03` carries because `verify_blocks_per_query = 0` on all 65 ON turns and its
  native KV and draft settings resolve identically under P405; smoke 10 already carried it to `da27f0ef`); the smoke must pass
  on `7207179b` or Fable gets a full run; (2) `Qwen3.8-27B-mlx-uniform-4bit`; (3) `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`;
  (4) `Ornith-1.0-35B-mlx-uniform-4bit` — each (2)–(4) its own smoke, gate and full run. The CLI and every smoke / full binding
  carry exactly ONE entry; no entry is restored on evidence from an older production pin (Fable only through its
  `7207179b` regression smoke + C188). Projection (V13): per phase from the smoke's measured components × full-run
  cardinalities (E1c cells, E2 20 items + 4 straddles, E7a 20, E7b 5) plus an explicit E7 tail reserve (one full-budget
  runaway per entry ≈ 1–2 h); the gate compares the nominal projection with 3.5 h, and a total-wall watchdog stops a
  campaign at its AUTHORIZED WALL CAP (nominal + one reserved tail) — exhausting it yields ABORT / INCOMPLETE and an operator
  disposition (v13 V17: one reserved tail is an allowance, not a worst case; several E7 requests can each reach their
  watchdogs). Nominal ≈ 10.5 GPU h for all four campaigns; ≈ 13.5–16.5 h with one reserved tail per full campaign; an entry projecting > 3.5 h goes to the operator. No Ornith estimate
  from its 3B active parameters — its smoke sets it.
- **Tuples:** `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` — `qwen3_5` dense hybrid, TurboQuant 4-bit KV (P405), per-query
  (harness `verify_policy=None` + an argv check that the scan resolves to `per_query`), drafter
  `caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter`. `Ornith-1.0-35B-mlx-uniform-4bit` — `qwen3_5_moe` (40 layers, full
  attention every 4th, 256 experts / top-k 8 + shared), native KV, per-query, TRANSPLANTED drafter
  `caslca/Ornith-1.0-35B-mlx-uniform-4bit-mtp-drafter` (split via `--model-type qwen3_next`, M27).
- **Registry states and overlay (v11 V5, v12 V10):** ONE shared byte-state generator (harness module, used by
  `Campaign.prepare`, the overlays and the fork's live-registry test) models each entry's MTP-OFF form as an ATOMIC raw-byte
  substitution of the pinned golden fixture: Fable's three-line C177 block (`draft_kind`, `draft_model`,
  `mtp_verify_scan: joint_v1`), `Qwen3.8-27B-mlx-uniform-4bit`'s C177 pair, and each P406 pair (the `draft_kind` line → the
  commented line with the `P406 INTERIM (C191 2026-10-20)` marker; the ADJACENT `draft_model` line commented; bytes otherwise
  unchanged). The accepted live registries are EXACTLY the 2⁴ = 16 combinations (each entry ON or OFF independently); a half
  applied atomic block, an altered comment / path / whitespace / newline, a duplicate marker or any other edit refuses —
  `Campaign.prepare` itself enforces it (not an opt-in test). Each overlay sets its entry ON (replaces that entry's atomic
  block with the fixture's bytes) and asserts the restored block equals the fixture block. §5's field-based rules are replaced
  by this generator.
- **Model pins and certified identity (v11 V6, v12 V11):** verified 2026-10-20 from the Hugging Face commit history — for all
  four repos (`caslca/Ornith-1.0-35B-mlx-uniform-4bit{,-mtp-drafter}`, `caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit{,-mtp-drafter}`)
  every file except `README.md` and `evaluation/M44-evidence-2026-09-14.json` is byte-identical (LFS sha256 / blob id) between
  the certification-time revision (drafters: Ornith `5279f90a` 2026-09-01 = the M27 upload, Qwen3.6 `fb07d16d` 2026-08-25 = the
  M6b upload; targets: Qwen3.6 `eee677f5`, Ornith `d2c948e0`) and the current head; the same comparison is made for the two
  Qwen3.8-27B picks' repos before their campaigns. A reviewed `dev/p369_phase2/pins.json` records, per entry, those
  revisions and every loaded file's sha256 (weights, configs, tokenizer, chat template, generation config); smoke and full run
  refuse any other file. Residual (recorded): the M6b / M27 runs loaded LOCAL extracted drafter directories before the
  uploads, so "upload = certified" rests on the upload procedure, not a recorded hash; the M27 extraction manifest is not on
  record. Mitigation, mandatory: the router-chain re-certification before restore (§3.1 Restore) must reproduce the certified
  predictor — acceptance not below the certified level (M6b 0.923, M27 0.778 point estimates) and decode speed-up ≥ 1.3× —
  else the predictor re-qualifies (M6d) instead of inheriting M6b / M27. The executable gate (v13 V16) is delegated to the
  reviewed router re-certification plan: pinned prompts / seeds and block size, the acceptance estimator and denominator, the
  numeric historical interval endpoints recovered from the M6b / M27 records, and the exact speed statistic for 1.3×. The worker asserts on the LOADED drafter (not
  only the target): `qwen3_5_mtp`, the certified depth and block size and effective proposal width, hidden / vocabulary dims
  and embedding / head binding to the target; for Ornith additionally `Qwen3_5MoeDecoderLayer` drafter layers, 256 experts /
  top-k 8 and int4 / g64 quantization.
- **Ornith drafter construction (v12 V12, v13 V14), before any GPU minute:** a tiny split → strict load → bind to a tiny
  `qwen3_5_moe` target → one draft / verify round test, with the source configuration's root and nested `text_config.model_type`
  pinned: (a) the uploaded drafter's shape (nested `qwen3_5_moe_text`) loads as `Qwen3_5MoeDecoderLayer` with expert count /
  top-k, all three routed projections and the quantization asserted; (b) ADVERSARIAL: a nested `qwen3_next` source (what
  `Qwen3NextMTPSplitter` preserves today; `Qwen3_5MTPConfig` builds MoE layers only when the nested type contains `moe`) must
  either be rewritten deterministically to the MoE runtime type or fail during splitting — never emit a dense-runtime artifact
  holding expert weights. The same architecture assertions run on the pinned real Ornith drafter at load. If (b) exposes a
  production defect, its fix is its own proposal, creates a NEW production pin and reopens the C188 carry-over assessment for
  every campaign already run.
- **Ornith drafter execution (v13 V15):** the drafter's MoE path (`Qwen3_5MTPDraftModel.draft_block` →
  `Qwen3_5MoeSparseMoeBlock` → `SwitchGLU.__call__`) is distinct from the target verifier's (`_switch_glu`, direct
  `SwitchLinear`). The tiny round gives it a SEPARATE draft scope and asserts runtime calls to its router, shared expert and all
  routed gate / up / down projections, with selected-expert evidence; sabotage negatives for each path make the test fail. The
  real Ornith smoke records the same positive draft-path inventory, separately from the target-verifier telemetry, and the
  smoke gate requires it.
- **Items (v11, V4):** no C84 bundles exist for either entry. E2 / E7 use a reviewed BORROWED PANEL fixture
  (`dev/p369_phase2/borrowed_panel.json`): per item the source bundle path (under `Qwen3.8-27B-mlx-uniform-4bit`) and its sha256,
  the item id, seed, dataset revision and content hash, and the canonical built-message sha256; per entry its templated token
  count and digest, precomputed with the pinned tokenizer BEFORE any GPU minute and bound into smoke-to-full authorization. A
  live reconstruction differing from the fixture refuses. E2 decides as in §3; E7a / E7b are a "synthetic borrowed-panel
  incidence record" — descriptive, never an estimate of how often events occurred while the entry served.
- **Ornith observability, before any GPU minute (v11, V3), test-first on a tiny `qwen3_5_moe` fixture:** (a) the loaded target
  is structurally MoE — model class, layer count / type census, full-attention / GDN split, MoE block count, expert count and
  top-k asserted; (b) one complete MTP request exercises recorder rows, accepted / rejected and bonus emission cuts, commit
  snapshots, neutral probes and verifier block boundaries; (c) the kernel inventory classifies the router gate, the shared
  expert and EACH routed bank projection (gate / up / down) exactly once per invocation in verifier scope, for both
  `SwitchLinear` and `QuantizedSwitchLinear` — coverage per routed-bank invocation, not "all experts observed"; (d) width-2 /
  width-3 verifier execution is bitwise-compared with sequential singleton execution on independent caches (routed output,
  target rows, selected expert indices, final state) — the MoE analogue of P400, measured not assumed; (e) negative tests that
  disable each new hook or omit a routed projection make the harness fail.
- **Smoke positives:** the KV positive follows the exact manifest (P405 F3): `tq_norm` for
  `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, `old_prefix_k` for Ornith.
- **Restore (v11, V7):** a worker PASS changes NO registry line. Per entry: worker PASS → reviewed fork push + submodule bump →
  reviewed router-chain ON / OFF re-certification against the pinned tuple → only then the exact restoration of that entry's
  C177 or P406 pair (and its registry-dependent tests, e.g. `test_opencode_probe_seeding.py`). FAIL, ABORT or INCOMPLETE
  keeps it MTP-OFF and goes to the operator with the measured bound.

## 4. Estimate (Q25)

E1c (v6, Q40): four trajectories per cell (ON, OFF1, OFF2, cross-load OFF) ⇒ ≈ 430K prefill tokens and ≈ 3.2K decode /
replay steps per pick, plus full-state SHA-256 at every commit on all four (≈ 450 GB per trajectory per pick for Fable at
≈ 2 GB/s ⇒ ≈ 4 min each, doubled by the probe-neutrality hashes; uniform ≈ ¼) and one probe forward per commit; E2 (v8) three trajectories in the ON process + one cross-load OFF arm ×
20 items × 512 tokens + four trajectories × ≈ 107K straddle prefill per pick (v7: three arms + two; ≈ +2 straddle sets); E7a ≈ 11–14 min per pick from C84 history with a
heavy-tail allowance (one 102,400-token runaway ≈ 1–2 h — bounded by the per-request watchdog, reported as censored).
Reserve **3–3.5 h of GPU time** plus harness build, review and suites (≈ half a session); the smoke's calibration revises
it, and a revised estimate above 3.5 h goes to the operator before the full run. The handoff's "≈ 1 h" and v1's "≈ 100 min"
were optimistic.

## 5. P387 (fork tests vs the C177 registry), revised by Q26

Measured: against the live MTP-OFF registry the P369 tests give 56 failed + 9 errors + 1 collection error (the worktree hides
it: no sibling ⇒ pinned fixture). Revised fix (test-only, red first, before the fork push): ordinary tests are DETERMINISTIC —
both the certified MTP tuple and the sampling come from the pinned golden fixture, and the presence of a sibling checkout no
longer changes the normal suite. A separate opt-in live-registry test (`MLX_REQUIRE_STACK_REGISTRY=1`) compares the live
registry with the fixture field by field and accepts exactly two states: identical, or the C177 interim — only `draft_kind`,
`draft_model` and Fable's `mtp_verify_scan` absent, where (Q34) each pick's commented `draft_kind` line and Fable's commented
`mtp_verify_scan` line carry the `P369 INTERIM (C177` marker and the commented `draft_model` line ADJACENT to that pick's
marked `draft_kind` equals the fixture's `draft_model` exactly (the registry's `draft_model` lines carry no marker; the
registry is not edited). v12 (V10): SUPERSEDED for v10+ runs — the live-registry test and `Campaign.prepare` use the shared
byte-state generator of §3.1 (the 16 per-entry ON / OFF combinations); the field-based rules above describe the original
P387 test only. C182 approved the v1 variant
(sampling from the live registry); this change goes back to the operator.

## 6. After this phase

Results → `docs/open-questions.md` P369 + handoff. Then fork push (operator) → submodule bump (full suites in both repos) →
per-pick re-certification ON vs OFF on real router chains (own plan, Cursor review, operator GPU go) → restore MTP-ON per
entry that passed both (its C177 or P406 pair + `test_opencode_probe_seeding.py` expectation; §3.1 Restore) → P368 layers 2–3.

# P369 phase 2 — GPU conformance run plan (E1c, E2, E7) — PLAN v1, 2026-10-18

Status: v1 → Cursor `gpt-5.6-sol-high` plan review. Parent: `docs/specs/p369-mtp-certification.md` (v3) §E1c, §E2, §E7.
GPU go: C175 (covers this phase only). Code under test: fork `p369-mtp` at the commit that clears the round-8 confirmation
review (round 7 tip `124de41f`). No serving-configuration change: the daily driver stays MTP-OFF (C177); no router runs.

## 1. What this phase decides

- E1c (acceptance): per pick, on real weights at the deployed tuple, MTP-ON's verifier distributions AFTER sampling
  transforms and its committed state equal plain singleton decoding at the same positions — or the claim becomes "bounded
  non-neutrality" with the measured bound and goes to the operator.
- E2 (supporting): greedy ON vs OFF token identity per pick.
- E7 (supporting, incident record only): how often the pre-fix M3 / M4 conditions occur on real traffic.

## 2. Harness (built first: test-first, Cursor code review, full fork suite twice — before any GPU minute)

Fork-only, test-only code; no production source changes.

- `dev/p369_phase2.py` — the driver. One process per (pick, arm); one resident model; refuses unless `:8000` is free and no
  `mlx_vlm.server` / `mlx-serve` / `pytest` / `opencode` process runs (pids by executable, own pid excluded).
- **Worker fidelity:** the worker argv comes from mlx-serve's own `config` loader + `process_manager._build_command` applied to
  a harness-local overlay of `main_models.yaml` that restores exactly the three C177 lines for the pick (`draft_kind: mtp`,
  `draft_model`, Fable `mtp_verify_scan: joint_v1`); the OFF arm uses the same overlay minus them (= today's registry). The
  argv is run through the fork's own `mlx_vlm.server.cli.main` with `uvicorn.run` intercepted to capture the app; requests go
  through `TestClient(app)` (lifespan preload) with `X-MLX-VLM-Chat-Id`, i.e. the real endpoint, templating,
  `_process_cached_request` and `stream_generate`. `MLX_VLM_CACHE_SESSION_MAX=1`, `APC_ENABLED` absent; both asserted in
  process. The mlx-serve router layer itself is NOT exercised (it is in the per-pick re-certification that follows, on real
  router chains).
- **Observers (test-local wrappers, values returned unchanged; Q12 / Q13):**
  - ON verifier: wrap `lm.speculative_logits_from_hidden` and `_mtp_verify_target` to record, per verify call, the cache
    offset at entry, the verify input ids and the logits rows; positions keyed absolutely (offset + row).
  - Plain reference: a sequential clean replay in a fresh process-state (fresh `PromptCacheState`, deployed preallocation,
    never a clone of a 262K cache) through the OFF path's `stream_generate` with a recording + forcing logits processor that
    records the raw logits at each step and forces the ON-emitted token, so the replay walks the identical history one token
    at a time (singleton decode).
  - Transform: both sides go through `_PositionedTargetSampler._filter` with the pick's deployed temperature / top_p / top_k
    / min_p; compared on positions whose history equals the emitted history (accepted drafts + bonus; rejected-draft rows are
    recorded, not compared).
  - State checkpoints (Q12): at the first commit past each threshold and at the end of each request, and at the same
    offsets in the replay: per-layer cache offsets, sha256 of the valid KV prefix bytes and of the GatedDeltaNet recurrent
    state bytes (never unused preallocated tails), plus next-step singleton logits for one fixed probe token on both sides.
  - Counters: the verify-scan module's `verify_blocks_*` / `verify_fallback_reasons`; branch spies on the
    `quantized_verifier` and dense `exact_speculative_verify` kernels (Q14) — which kernels the real tuples hit is recorded.
  - E7: a wrapper around `speculative.mtp._mtp_plain_emission` records per verified block `(len(tokens), n_emit, accepted,
    terminal, cause ∈ stop|budget|forced|none)`; classes: **M4a** stop on an accepted draft with ≥ 1 verified token after it
    (pre-fix: committed past the stop), **M4b** terminal on the verifier bonus or the first token (pre-fix: terminal token left
    out of the cache, next turn diverged), **M3** a forced token inside a block (pre-fix: overshoot up to a block).
- **CPU tests (in the suite, tiny fixtures, red first):** argv equality with mlx-serve's `_build_command` for both picks and
  arms; the overlay touches only the three C177 lines; comparator positives — a 1-ulp perturbation of one verifier logit at
  one position, a swapped KV byte, a changed recurrent element and a changed next-step logit are each detected; a
  rejected-draft row is not compared; scripted M3 / M4a / M4b events on the tiny hybrid fixture are counted exactly (and zero
  on a plain run); refusal on a live `:8000` owner.

## 3. Runs (per pick: Fable first, then uniform)

Tuples (registry as of `main_models.yaml` at the run commit + the C177 restore): **Fable** native16 KV (`kv_bits: 0`,
TurboQuant scheme off), `joint_v1`, prefill 512, `fused_v1`, lazy embeddings, prealloc 262144, drafter
`caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter`; **uniform** TurboQuant 4-bit KV, `per_query`, prefill 512,
prealloc 262144, its registered drafter. Weight revisions and file sha256 recorded from the HF cache before load.

- **Smoke (≈ 5 min):** Fable E1c on the 1,024 straddle prompt + E2 on 2 frozen prompts, both arms; the comparator's injected
  1-ulp positive must fire on the live data. Then the full sequence.
- **E1c:** prompts of length T − 64 for T ∈ {1,024; 8,192; 32,768; 65,536} (deterministic text, generator + seed recorded) plus
  one short chat prompt; deployed sampling, fixed seed; 160 generated tokens so verify blocks cross T. ON pass, then the
  clean replay. PASS per pick: zero output-relevant mismatches (any difference in a filtered distribution: support or value,
  bitwise) on every compared position; every checkpoint hash and next-step logit equal; Fable: `verify_blocks_straddle > 0`
  on each straddle prompt and an empty `verify_fallback_reasons`; uniform: boundary lengths and per-query / TurboQuant routing
  recorded. Raw-logit max |Δ| reported descriptively. On FAIL: finish that pick's E1c prompts (to measure the bound), skip its
  E2 / E7, stop and report.
- **E2:** the C84 item set (20 per pick: the five ids per axis in
  `benchmark/results/<pick>/{math500,humanevalplus,mbppplus,cjudge}.c84bundle-after-native16-20260914.jsonl`). The raw frozen
  request file is NOT on this box (it stayed in the C84 box's workdir), so requests are rebuilt with the stack bench's own
  prompt builders and the rows' `sampler_seed`; each rebuilt prompt's token count must equal the row's `prompt_tokens`, else
  that item is replaced by nothing and reported. Temperature 0, `max_tokens` 512 (identity of the first 512 tokens; thinking on), plus the 1,024 and 8,192 straddle
  prompts at 160 tokens; three fresh loads per pick: OFF, ON, OFF again (same-arm reload control). PASS: ON == OFF token ids on
  every request, given the control is identical; if the control differs, E2 is informative only (recorded, not blamed).
- **E7a:** the same 20 rebuilt requests per pick at deployed sampling with their recorded seeds, MTP ON, full deployed budgets
  (natural termination), each through the cached-session path. **E7b (time-boxed 10 min per pick):** two stored tg1 / M63
  opencode sessions per pick replayed turn by turn with the recorded history (the model generates each assistant turn to its
  natural stop; one forwarded chat id). Report per class: events / opportunities with request- and accepted-block
  denominators and Clopper–Pearson 95 % upper bounds (zero events → ≈ 3/n).

## 4. Machine state and supervision

Stack stopped and `:8000` free (verified), zero worker / bench / pytest processes, quiet box; `pmset -g ac` (140 W / 28 V) and
battery > 20 % logged at start and by the monitor (no latency claim is made; recorded for provenance). Launched detached
(`nohup`, pid recorded, exit code preserved), background waiter, no foreground sleep. A daemon (`benchmark/m1/bench_watch.py`
or an equivalent writer in the run dir) logs every 5 min: phase / item progress, ETA vs the estimate, errors, mismatch and
event counts, power. Outputs under `$STACK_WORKDIR/p369/phase2/<run-id>/`: manifest (fork commit, MLX / Metal 0.32.3,
weights revisions + sha256, argv + env per process, overlay sha256, prompt generator + seeds), raw observer records, results
JSON, monitor log. Portable paths only; privacy-scanned before anything is committed.

## 5. Estimate

Per pick: E1c ≈ 11 min (two ≈ 106K-token prefill sets + ≈ 1.6K decode / replay steps), E2 ≈ 15 min (three loads), E7a ≈ 12–15
min (C84 history: 668 s / 821 s for 20 items MTP-ON), E7b ≤ 10 min ⇒ ≈ 50 min per pick, ≈ 100 min total + loads, heavy-tail
allowance for E7a runaways (max_tokens 102,400). This exceeds the handoff's "≈ 1 h"; the trimmed variant (no E7b, no reload
control on uniform) is ≈ 75 min.

## 6. Separate item found while planning — P387 (fork tests vs the C177 registry)

The fork's P369 tests read the LIVE sibling registry when it exists (`tests/test_mtp_verify_scan.py::_stack_registry`) and
`deployed_sampling()` asserts `draft_kind == mtp`. From `~/ws/mlx-vlm` (sibling = the stack checkout, MTP-OFF under C177)
those modules give 56 failed + 9 errors + 1 collection error (measured with `MLX_STACK_REGISTRY` pointed at the live
registry), so the full fork suite cannot pass from the main checkout or at the submodule bump. The worktree hides it (no
sibling ⇒ pinned fixture). Proposal (test-only, red first): the P369 tests take the MTP tuple they certify from the pinned
golden fixture (the shipped-when-ON tuple) and the sampling defaults from the live registry, asserting the live sampling
equals the fixture's; `MLX_REQUIRE_STACK_REGISTRY=1` keeps its equality check but accepts exactly the C177 interim (the three
draft lines commented with the `P369 INTERIM (C177` marker) as equal. Built before the fork push.

## 7. After this phase

Results → `docs/open-questions.md` P369 + handoff. Then fork push (operator) → submodule bump (P387 fixed; full suites in both
repos) → per-pick re-certification ON vs OFF on real router chains (own plan, Cursor review, operator GPU go) → restore
MTP-ON (C177 lines + `test_opencode_probe_seeding.py` expectation) → P368 layers 2–3.

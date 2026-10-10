# M58 build review 1 (Claude, cold, adversarial) — 2026-10-06

Heads reviewed (as briefed): fork `m58-joint-verify` @ `1202ac6c` vs `fbe2775e`; router `m58-joint-verify` @ `5f32c9f` vs `7be6bfd`; stack worktree `m58-provenance` @ `0e8e694` (merge-base `4d10dc8`).
**The fork moved during review:** `099053ad` ("review round 1") landed at 20:43 and the stack worktree has uncommitted test edits (conftest pin made opt-in). Findings below are against the briefed heads. Each one says whether `099053ad` or the in-flight diff appears to fix it. Neither change was reviewed in full; both need their own pass.

Commands run (all CPU or mocked; no servers, no loads, nothing sent to :8000): fork M58 suites, 102 passed at `1202ac6c` (both suites import the autouse `_cpu_device`, `test_attention_policy.py:31-38`); 10 runtime-patch mutations via `-p` plugins under `$STACK_WORKDIR/m58/tmp/claude_review/plugins` (no repo edits); router `tests/`, 178 passed; stack M58 plus related provenance/compare/capacity/parity suites, 494 passed. A byte comparison of the serializers against `main`'s `schemas.py` is identical with and without M57 counters (VERIFIED).

## Verdicts

- **Fork: FIX-THEN-SHIP.** F1 and F2 are real at `1202ac6c`; `099053ad` appears to fix both. F4 and F5 remain (LOW).
- **Router: SHIP.** R1 is LOW and follows the M57 precedent.
- **Stack: FIX-THEN-SHIP.** S1 and S2 are MEDIUM and still present at `0e8e694`. The in-flight edits do not touch `provenance.py` or `parity_replay.py`.

## Findings

**F1 MEDIUM — the self-test's straddle known positive passes on non-finite output.** VERIFIED (code read). Fixed in `099053ad` (`_invalid` now fails the self-test outright).
- Evidence: `mlx_vlm/mtp_verify_scan.py:143-152`. `_differs` folds a non-finite value into "differs". `self_test.both` returns that flag (`:447-448`), and the straddle check takes it as "the mismatch occurred" (`:465-470`).
- Failure: a kernel that returns NaN or Inf at the 1023→1025 cell is predicted and "occurs", so the load passes. The first cell would catch NaN only at 2048 keys.
- Fix: in the self-test, fail on shape, dtype or non-finite problems; compare bits only on valid outputs.

**F2 MEDIUM — the `draft_kind` refusal checks the configured value, not the resolved drafter (JC6).** VERIFIED (code read). Fixed in `099053ad` (`require_loaded_mtp_drafter`, called after resolution at `generation.py:1537`).
- Evidence: the policy is stamped and self-tested at `mlx_vlm/server/generation.py:1446-1450` with `draft_kind` taken from the flag or env. Later, `load_drafter` may substitute another kind with only a warning (`:1499-1508`). `drafter_incompat_policy` may return `(None, None)` under `MLX_VLM_DRAFT_ALLOW_FALLBACK=1` (`:1514`).
- Failure: `joint_v1` stays stamped while a non-MTP drafter, or no drafter, serves. That domain was never qualified (Claude S11).
- Fix: re-check `draft_model is not None and draft_kind == "mtp"` after resolution and `_fail` before READY.

**F3 LOW — the AB counters advance before materialisation, and an exception leaks pending entries.** VERIFIED. Fixed in `099053ad` (counters move in `end_block`; `discard_pending` runs in a `try/except` around `_model`).
- Evidence: `mlx_vlm/mtp_verify_scan.py:274` increments `verify_ab_*blocks` at shadow time; the spec says "materialised before the counters advance". `speculative_verifier.py:407-418` calls `end_block` only on the success path.
- Failure: pending flags from an aborted round are evaluated and counted at the next request's `snapshot()`, which misattributes them.

**F4 LOW — the quantized-KV refusal checks only `kv_bits`.** VERIFIED (code read). Still open in `099053ad`.
- Evidence: `mlx_vlm/server/generation.py:1449` and `mtp_verify_scan.py:383` check `kv_bits` only. `kv_key_bits`, `kv_value_bits` and `kv_quant_scheme` (TurboQuant) pass the load.
- Impact: the runtime still falls back with reason `cache` (`mtp_verify_scan.py:197-204`). Served numerics do not change silently, and G1a would fail on `verify_blocks_joint_v1 == 0`. The spec's "refuse at load" is still violated.
- Fix: refuse if any of those fields is set.

**F5 LOW — no counters on the continuous-batching path.** VERIFIED that the code exists; ASSUMPTION on how often it is used.
- Evidence: snapshot/since are wired only in `_process_cached_request` (`generation.py:1796-1801`, `1954-1959`). Requests without `prompt_cache_state` go through `BatchGenerator`/`_step` (`:2602-2620`, `:2908ff`), which still passes the MTP drafter.
- Impact: those responses carry no `verify_*`, and their blocks land in any cached request's window that is open at the same time. Gates read absent counters as failures (loud), so this is not a validity hole. Same gap as M57.
- Fix: document it, or wire `since` in `_step`.

**F6 INFO — rule 7 is valid only because the domain pins GQA 6.** Mirror semantics VERIFIED; MLX `n_simds = gqa × qL` is an ASSUMPTION from the MLX source as I recall it.
- Evidence: `_qwen3_5_sdpa_vector_plan(seq_len, q_heads, kv_heads)` (`language.py:528-533`) models the qL=1 dispatch (`n_simds = gqa`, `:500`). The predicate in `mtp_verify_scan.py:240-241` calls the same function with the same argument convention as the ragged dispatch (`language.py:674`), on every call, using the live mirror.
- Why it holds today: block counts agree for the joint call only because `devc == 's'` and gqa 6 already exceeds the `n_simds > 4` cut (`:503`).
- Risk: widening `Domain.gqa` to ≤ 4 breaks rule 7 silently, though the 2048-key self-test cell would refuse the load.
- Fix: add a comment or assert tying `QUALIFIED_DOMAIN.gqa` to this condition.

**F7 NIT — hot path.** `_device_class()` calls `mx.device_info()` on every classify (16 layers × every round). After `099053ad` it is called twice. Cache it at policy construction; the mirror already caches it (`language.py:492`).

**F8 NIT — AB mismatch log fields.**
- `layer=` is the ordinal of shadowed blocks, not the layer index (`mtp_verify_scan.py:275`).
- "Once per shape" keys on `key_length`, so in practice it logs once per mismatching round.
- `_logged_shapes` grows without bound.

**F9 NIT — length 2 with `mask=None`.** Today's branch passes `None` (non-causal) to SDPA (`speculative_verifier.py:127-142`). `joint_v1` maps it to `"causal"` (`mtp_verify_scan.py:208, 233`). Production masks for N>1 are `"causal"` (`models/base.py:263-277`; ASSUMPTION that every cache `make_mask` does the same), so this is unreachable in practice. Note it in the spec.

**R1 LOW — router joint_v1 validation checks `kv_bits` only.** `mlx-serve/src/mlx_serve/config.py:175` checks `kv_bits`, but `kv_quant_scheme` is emitted independently (`process_manager.py:154-155`). Same as M57 `fused_v1` (`config.py:150`). The worker falls back with reason `cache`. Optional fix: reject a non-empty `kv_quant_scheme` under `joint_v1`.

**S1 MEDIUM — AB gate rows can be stamped `joint_v1` and pool with latency rows.** VERIFIED (code and tests); ASSUMPTION that the worker loads lazily.
- Evidence:
  - With no live worker, the registry branch returns `declared` without `+ab` (`benchmark/bench/provenance.py:883`; the `+ab` is applied only to `compared`, `:948-952`). This is pinned by `test_ac10_registry_never_yields_the_ab_value`.
  - `generate.run` stamps manifests before any request (`generate.py:474`), so a fresh router has no worker yet.
  - `test_ac10_only_value_not_source_enters_the_v8_fingerprint` shows a `joint_v1`/registry row is compatible with a `joint_v1`/worker row.
- Failure: a `generate` run under the AB overlay records `joint_v1` and pools or compares with latency-arm `joint_v1` rows. This violates R6, the very thing the fingerprint value exists to prevent.
- Fix: when the entry declares `mtp_verify_ab: true`, return `joint_v1+ab` from the registry too, source `registry`. Over-labelling a gate row is safe; under-labelling is not. Alternatively, refuse when AB is declared and no worker is observed. Update the spec line "never from the registry" to match.

**S2 MEDIUM — `parity_replay` can let G1b "pass" on nothing.** VERIFIED (ran `compare` on two zero-row docs → `pairs=0 … rc 0`).
- Evidence:
  - `run` accepts an empty selection: a `--models` typo gives `reqs == []`, `sorted([]) == sorted([])`, and the replay is written as complete with 0 rows (`parity_replay.py:141`, `:216`).
  - `compare` treats an empty `expected` as the union of rows (`:257`).
  - `compare` never checks either doc's `status` (an `aborted` B is accepted) and returns 0 when `same + diff == 0` (`:290-292`).
- Fix:
  - `run`: refuse (rc 2) when `reqs` is empty.
  - `compare`: rc 2 when `pairs == 0`, when either `status != "complete"`, or when the two docs' `expected_keys` differ.

**S3 LOW — the worker command line can be recorded as `null`.** `worker_serving_facts` returns `None` for no worker, an unreadable registry or a missing model (`provenance.py:966-978`). `parity_replay.py:188` stores that silently, and `test_m50_entrypoints.py` stubs exactly this case to pass. AC11 requires the worker flags per request, and after a successful response a worker must exist. Fix: abort when the result is `None`.

**S4 LOW — the auth header is half-wired.** `_post` sends a bearer token (`parity_replay.py:48-52`), but `client.preload` does not (`client.py:80-83`), and mlx-serve enforces auth router-wide (`router.py:63`). With `MLX_API_KEY` set, the preload at `parity_replay.py:172` raises outside any `try`: the run dies with a traceback and the journal is not marked aborted. Fix: add the header in `client._post`, or wrap the preload in `_abort`.

**S5 LOW — `compare_predictor` accepts `joint_v1+ab` as an arm.** `compare_predictor.py:57` lets `mtp_verify_scan` differ, including `per_query` vs `joint_v1+ab`, and the tool reports tokens/wall/decode ratios. R6 says AB rows are never latency rows. Fix: refuse any `+ab` side in `compare_predictor` and in latency metrics of `compare`.

**S6 LOW — the autouse conftest seam.** `benchmark/bench/tests/conftest.py:88-106` at `0e8e694`. Turning the pin off fails about 45 tests across 8 modules (run_capacity 9, run_reasoning* 18, run_retrieval* 16, orphaned_manifest 1, provenance_fingerprint 1), so the pin is load-bearing.
- Why it is not a validity hole: production `unknown` is a loud refusal (`provenance.py:897`), and a resolver regression is caught by the marked tests.
- Why I still want it narrowed: it silently re-semantics every future test.
- Ruling: pin per module (opt-in). The uncommitted worktree edit does exactly this (`pin_mtp_scan`, non-autouse). Accept once committed.

### Checked and clean (VERIFIED)

- **Fallback code paths.** The per-query fallback is the old code: the hook returns `None` and the verifier's original branches run unchanged (`speculative_verifier.py:114-176`). `per_query_attention` (`mtp_verify_scan.py:114-136`) matches `main`'s per-query branch argument for argument. The straddling length-2 case is the only change of the served path (C120 ruling).
- **No new module under `per_query`.** `per_query` never stamps (`resolve_policy`, `:356-361`), so the hook is a `getattr` that returns `None`. `generation.py:213` does import the module under the default (inert).
- **No M57 leak.** No `policy`/`force_fused` reaches the joint call (`mtp_verify_scan.py:107-111`, `models/base.py:369-453`). M57's `policy=` is passed only by `Qwen3_5Attention.__call__` (`language.py:938`), which the verifier never calls.
- **AB instrument.** Both paths run from one prepared QKV, the joint output is served, and the same `joint_attention` object is used for production and AB (`:258-271`). Comparison is bitwise via uint16. Served values do not depend on AB.
- **Counters and serializers.** Counters live on the per-instance policy, not the verifier singleton (`apply_to_model`, `:389-407`). Every M57 serializer site has a matching M58 site (anthropic 2/2, openai 8/8, generation 10/10, schemas 5/5). The request-completed log suffix appears only when counters are present.
- **Router.** Validation and emission are correct. `type == "vision"` is required, and I accept that: otherwise a text entry could declare `joint_v1`, never emit the flag, and still get `joint_v1` registry provenance. Golden-command tests pass.
- **v8 compatibility.** A v7 manifest is compatible with v8 `per_query` and incompatible with v8 `joint_v1` and `+ab`, so `--clean-stale` leaves v7 rows alone under `per_query` (`provenance.py:568-590`, tests at `:211-235`). The `unknown` refusal reaches `assert_serving_state` (`:897`).
- **Mutations caught.** Bound 36, straddle disabled, `MIN_LENGTH` 3, step-mask OR, domain widened, AB serving per-query, value-equal (not bitwise) compare, `since` without reset, causal leak (`mask=None`), and a 3e-4 joint perturbation (AC8 catches it at 1e-4). Tolerance 1e-4 on CPU fp32 is acceptable: tokens, acceptance and offsets are asserted exactly, and bit identity is a GPU-gate property by spec (AC3b).
- **AC8 limits.** Drafts come from an oracle, so drafter outputs do not affect the run. The drafter cache is not explicitly restored ("reset by the rounds"). `099053ad` adds an unmodified-drafter variant that I have not reviewed.
- **Scope and markers.** `# Fork (M58)` markers are on every hunk (the second env line at `cli.py:738` relies on the hunk-level marker). No registry or `src/*` change, no PII or absolute paths in the diffs, and no remote-tracking branch contains the M58 commits.

## Judgement-call rulings

1. **Disjoint buckets, histogram on `per_query` only — ACCEPT.** `straddle` has its own counter.
2. **Reason names — ACCEPT.** Amend G1a: it cites `length<3` / `straddle` as reasons. With length 2 folded in and `straddle` as a bucket, the criterion becomes "`verify_fallback_reasons` empty inside the domain".
3. **4-D bool rows non-empty and contiguous, one sync — ACCEPT.** Conservative and rare. Note that the batch-1 `BatchKVCache` path may hit it every layer (F5 context).
4. **Count only `output is None` blocks; ragged blocks uncounted — ACCEPT.** Ragged blocks are batch/left-padded and outside the policy by construction.
5. **Straddling length-2 served per-query under `joint_v1` — ACCEPT.** This is the C120 ruling; `per_query` is unchanged.
6. **Check `draft_kind` at the flag/env only — REJECT** (F2). Fixed by `099053ad`; accept that fix.
7. **No eligible cell → refuse load — ACCEPT.** Stricter than a silent runtime fallback, and it is what makes "outside the domain cannot be served silently" true.
8. **One `verify_counters` dict, flattened, omitted when `None` — ACCEPT.** Byte identity against `main` VERIFIED.
9. **Log tokens only when counters are present — ACCEPT.**
10. **AB `end_block` with one mid-graph `mx.eval` — ACCEPT** for gate rows only (R6). The counter-advance ordering is fixed in `099053ad` (F3).

Stack (conftest autouse pin): **REJECT the autouse form, ACCEPT opt-in** (S6). The in-flight edit does this.

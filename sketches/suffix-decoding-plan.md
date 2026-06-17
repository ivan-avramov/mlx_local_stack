# Plan: SuffixDecoding (drafter-free speculative decoding) for mlx-vlm

**Status:** v1 implemented (2026-06-16). Drafter-free n-gram / prompt-lookup speculative
decoding for dense standard-attention models (gemma4 — dense + MoE). Code lives in the
canonical forks `../mlx-vlm` and `../mlx-serve` (parent-folder repos; the `mlx_local_stack/src/*`
submodules sync from them). v1.1 (hybrid Qwen3.6 / GatedDeltaNet) also implemented (2026-06-16);
see §8.

**Goal:** Add a *model-free* speculative decoder — no draft model, no trained MTP head, no
extra weights, no extra GPU memory — that proposes draft tokens from an n-gram / suffix
index over the prompt + tokens generated so far, and plugs into the **existing** speculative
verify + accept + rollback machinery. Target workload: reasoning + coding, where output
heavily echoes the input (editing files, repeating identifiers/imports, regenerating similar
blocks, structured output, agentic loops). This is the one speculative path the fork does
**not** already have (MTP/DFlash/EAGLE-3 are present; suffix/n-gram is absent — grep confirms
no `suffix`/`prompt_lookup`/`ngram_spec` anywhere in `mlx_vlm`).

Why this and not more MTP: MTP needs a model-internal learned head (`gemma4_assistant`,
`qwen3_5_mtp` only) and a matching checkpoint. SuffixDecoding works on **any** model with
zero memory cost — it's a data structure, not a network. On a 64 GB box where 256K KV is the
memory constraint, "free" speculation matters more than a draft model would. It is also
*complementary* to MTP: MTP predicts novel text, suffix matching predicts repeated text.

---

## Model-independence — what is and isn't model-specific

- **Proposer is fully model-independent.** The n-gram / prompt-lookup index has no trained
  head, no weights, no per-model drafter. It works on any tokenizer/model. This is the real
  contrast with MTP/EAGLE-3, which need a *trained drafter checkpoint* matched to the target.
- **Verify + rollback is shared speculative infra.** Every speculative method uses it, and it
  has a per-cache-architecture implementation that already exists in the target models:
  - Standard-attention (KV-only) models (gemma4): rollback = trim the appended K/V to
    `accepted+1`. v1 wires this.
  - Hybrid recurrent models (Qwen3.6 / qwen3_5 GatedDeltaNet; Mamba-style): rollback must ALSO
    restore the recurrent state, which requires snapshotting it during the verify forward. This
    is v1.1 (below).
- So suffix decoding is "drafter-free / model-independent" in the sense that matters: no
  training, no weights, no per-model network. The Qwen "extra" is not a trained component —
  it's reusing the target model's existing speculative-rollback hook for its cache type.

---

## 0. The correctness bar (non-negotiable)

Under **greedy** sampling, speculative output MUST be token-identical to non-speculative
greedy output. Speculation only changes *how many forward passes* produce the tokens, never
*which* tokens. Every test below enforces this. Under temperature > 0, use the existing
rejection-sampling acceptance path (`_speculative_walk_batch_deferred_greedy` and friends),
which preserves the target distribution.

---

## 1. Verified current state (the seam)

All anchors confirmed in `src/mlx-vlm/mlx_vlm`:

- **Dispatch into speculation:** `generate/ar.py:587-603` — when `draft_model is not None`,
  the loop hands off to `run_speculative_rounds(...)` and returns. Non-spec path is
  `ar.py:606-622`.
- **draft_kind routing (hardcoded, no abstraction):** `speculative/utils.py:71-80`
  (`get_speculative_rounds_batch`) and `:118-212` (`run_speculative_server_rounds`) branch on
  `draft_kind in ("eagle3","mtp","dflash")`. **There is no proposer interface** — we add a
  parallel branch.
- **MTP proposer contract (what we replace):** `speculative/mtp.py:608-617` —
  `draft_model.draft_block(bonus, hidden, shared_kv, block_size, sampler, token_dtype)` returns
  token ids `[1, bs-1]`. MTP also needs `hidden` and `shared_kv` (model internals) — **we
  need neither.**
- **Verify (reused, simplified):** `speculative/mtp.py:136-174` (`_mtp_verify_target`) builds
  `verify_input = concat([[bonus]], draft_tokens)` of shape `[1, 1+bs]`, runs the target LM,
  returns `_MTPVerifyResult`. For suffix decoding we run a *lighter* verify (logits only, no
  `return_hidden`/`return_shared_kv`).
- **Accept walk (reused as-is):** `_speculative_walk` (`test_speculative.py:967` exercises it)
  and `_mtp_acceptance_walk` (`mtp.py:393-427`) → `(accepted:int, new_tokens:List[int])`.
- **Rollback (reused as-is):** `mtp.py:667-681` → `lm.rollback_speculative_cache(prompt_cache,
  gdn_states, accepted, block_size)` trims the KV cache to `accepted+1` positions. Handles
  GDN (hybrid) state when `gdn_states` provided.
- **CLI:** `generate/dispatch.py:406-427` — `--draft-model`, `--draft-kind`
  (choices `["dflash","eagle3","mtp"]`), `--draft-block-size`. Auto-detect map in
  `speculative/drafters/__init__.py` (`DRAFTER_KIND_BY_MODEL_TYPE`).
- **Acceptance is LINEAR, not tree:** cache advances by `accepted+1` per round
  (`mtp.py:675`). v1 proposes a single linear best candidate — no tree attention.

**Key finding:** a token-only proposer is *strictly simpler* than MTP — it skips
`return_hidden`, `return_shared_kv`, the shared-KV slicing (`_slice_shared_kv_after_reject`),
and the drafter `set_shared_kv`/hidden plumbing. It reuses verify + accept + rollback
untouched.

---

## 2. Design

### 2.1 The proposer is a non-NN "draft_model"

Make `ar.py`'s existing `if draft_model is not None` branch fire by passing the proposer
object *as* `draft_model`. It is a plain Python object, not an `nn.Module`. `draft_kind =
"suffix"` routes it to the new rounds function. This reuses all existing plumbing (dispatch,
block-size knob, server wiring) with no changes to `ar.py:587-603`.

New module `speculative/suffix_decoding.py`:

```python
class SuffixDecodingProposer:
    """Drafter-free proposer. Indexes prompt + generated tokens; proposes the
    continuation that most-frequently followed the current suffix."""

    def __init__(self, *, min_match=2, max_match=8, max_draft=None):
        self._index = None          # built in reset()
        self.min_match, self.max_match = min_match, max_match
        self.max_draft = max_draft  # defaults to draft_block_size at call time

    def reset(self, prompt_token_ids: list[int]) -> None:
        self._index = build_suffix_index(prompt_token_ids)   # v1: dict of k-gram -> next span
        self._tokens = list(prompt_token_ids)

    def observe(self, emitted: list[int]) -> None:
        """Append accepted tokens so later turns can match against fresh output."""
        self._tokens.extend(emitted); update_index(self._index, self._tokens, emitted)

    def propose(self, context_suffix: list[int], max_draft: int) -> list[int]:
        """Return up to max_draft candidate token ids (possibly empty)."""
        return longest_freq_match(self._index, context_suffix, self.min_match, max_draft)
```

### 2.2 New rounds function (mirror MTP, drop the model-internals)

`speculative/suffix_decoding.py::run_suffix_decoding_rounds(...)` mirrors `_mtp_rounds`
(`mtp.py:523-681`) but:

1. `proposer.reset(prompt_ids)` once; then each round:
2. `draft = proposer.propose(recent_suffix, max_draft=draft_block_size)`. If empty → emit one
   normal token (no overhead beyond the cheap lookup) and continue.
3. `verify_input = concat([[last_token]], draft)`; run **lighter** verify: `logits =
   lm(verify_input)` (no `return_hidden`, no `return_shared_kv`), sample target tokens.
4. `accepted, new_tokens = _speculative_walk(draft, target_tokens, budget)` — reused.
5. `lm.rollback_speculative_cache(prompt_cache, gdn_states, accepted, bs)` — reused (trim KV
   to `accepted+1`).
6. `proposer.observe(new_tokens)`; advance position by `accepted+1`.

### 2.3 Config

- Add `"suffix"` to `--draft-kind` choices (`dispatch.py:417`). When `--draft-kind suffix` and
  no `--draft-model`, construct `SuffixDecodingProposer` internally (drafter-free).
- New optional knobs (env + CLI): `--suffix-min-match` (default 2), `--suffix-max-draft`
  (default = `draft_block_size`). Keep `--draft-block-size` as the max draft length.
- Server: expose via the same path mlx-serve already forwards draft flags through, or set per
  the standalone `:8092`/main subprocess args.

---

## 3. Design decisions (recommendations, open to override)

1. **Index structure — start with prompt-lookup (PLD), then suffix automaton.**
   - **v1 (recommended first):** k-gram dict `tuple(last k tokens) -> following span`, longest
     deterministic match. This is "prompt lookup decoding," proven, ~80% of the win on
     echo-heavy coding, and ~50 lines. Ship and measure before building more.
   - **v2:** full suffix automaton + frequency scoring (the actual SuffixDecoding paper,
     Oliaro et al. 2024) for better hit rate on partially-novel continuations.
2. **Corpus scope — prompt + this request's generated tokens.** Covers the dominant
   echo/repeat case. Cross-request corpus is deferred (it overlaps APC's territory and adds
   lifetime/eviction concerns — see the APC sketch).
3. **Linear, not tree.** Reuse the existing linear accept/rollback. Tree speculation needs a
   custom verify (tree attention mask) and is out of scope for v1.
4. **Target models for v1 — dense standard-attention first (the Gemmas).** Hybrid Qwen
   (GatedDeltaNet) is v1.1, not a rewrite: its recurrent state must be captured during the
   verify forward before rollback can restore it. Concrete plan in §8 (v1.1).
5. **Works alongside TurboQuant/quantized KV.** Suffix decoding changes *which tokens are
   proposed*, orthogonal to *how KV is stored*. No interaction with `kv_bits` (unlike APC).

---

## 4. Implementation phases

- **Phase 1 — proposer + rounds (no model):** `suffix_decoding.py` with v1 k-gram index and
  `run_suffix_decoding_rounds`. Unit-tested against a fake LM. ~1 day.
- **Phase 2 — dispatch + config:** branch in `speculative/utils.py:71-80` and `:118-212`; add
  `"suffix"` to `dispatch.py` choices; internal construction when drafter-free. ~0.5 day.
- **Phase 3 — integration on a real tiny model:** equivalence + acceptance tests. ~0.5 day.
- **Phase 4 — benchmark + Qwen/GDN (v1.1):** measure on coding-echo prompts via `benchmark/`;
  wire gdn capture for hybrid rollback.

---

## 5. Testing strategy (mirror `tests/test_speculative.py`)

**Unit — proposer (pure data):**
- `test_suffix_propose_exact_repeat`: index a stream containing `[... A B C D ...]`; query
  suffix `[A,B]` → propose `[C,D,...]` up to max_draft.
- `test_suffix_propose_no_match_returns_empty`: novel suffix → `[]` (graceful, zero overhead).
- `test_suffix_propose_min_match_threshold`: matches shorter than `min_match` → `[]`.

**Unit — rounds against a fake LM** (mirror `test_speculative_walk_batch_deferred_greedy`,
`test_speculative.py:1276`, and the walk test at `:967`):
- Fake LM whose argmax follows a known script. Feed a proposer pre-seeded to draft a partly-
  correct block. Assert `accepted` count, `new_tokens` order, and that the KV cache was
  trimmed to `accepted+1` (mock `rollback_speculative_cache` and assert args).

**Integration — equivalence (the correctness bar):**
- `test_suffix_decoding_matches_greedy`: tiny real model, repetitive prompt ("repeat this code
  block verbatim N times"). Generate with `draft_kind=None` and `draft_kind="suffix"`,
  greedy. **Assert token-identical output.** This is the gate.
- `test_suffix_decoding_accepts_on_repeat`: same run, assert acceptance rate > 0 and forward-
  pass count < token count (proves it actually sped anything up).

**Benchmark (not a unit test):**
- Add a coding-echo task to `benchmark/` (or a one-off via `eval_harness.py tasks`): decode
  tok/s with/without suffix decoding on (a) an edit-existing-file prompt, (b) a novel-prose
  prompt (expect ~no gain — confirms graceful degradation, not regression).

---

## 6. Risks / gotchas

- **Verify still runs a full forward pass per round.** The win is *fewer rounds* when tokens
  are accepted, not cheaper rounds. Low acceptance ⇒ no speedup (but the k-gram lookup is
  ~free, so no *regression* either — confirm in the novel-prose benchmark).
- **Acceptance is low on genuinely novel text.** Expected; that's why rapid-mlx quotes a
  modest 1.1–1.5×. The coding-echo case is where it pays.
- **Hybrid (Qwen GDN) rollback** needs `gdn_states` captured in verify. v1 targets dense
  Gemma; v1.1 sets the capture flag and reuses the existing gdn rollback — not a rewrite.
- **Sampling correctness (temp > 0):** must route through the rejection-sampling walk, not a
  naive equality check, or it biases the distribution. Covered by reusing the existing
  deferred-greedy/sampling walk.
- **Interaction with the session prompt cache:** the proposer indexes the *full* prompt
  including the cached prefix; ensure `reset()` is fed the full token id list, not just the
  uncached suffix.

---

## 7. Acceptance criteria

1. Greedy output is byte-identical with and without suffix decoding (equivalence test passes).
2. Acceptance rate > 0 and measurable decode-tok/s gain on the coding-echo benchmark.
3. No decode-tok/s regression on the novel-prose benchmark (graceful degradation).
4. 36/36-style green: new unit tests pass, existing speculative tests unaffected.

---

## 8. v1.1 — Hybrid (Qwen3.6 / GatedDeltaNet) support

**Status:** implemented (2026-06-16). Shipped: mlx-vlm `fd1948c`, mlx_local_stack `b9d9bca`.
The gap / fix / steps below are the original plan, kept as history; annotations note how each
shipped.

### Outcome

- Fix landed as designed: a per-target hook `LanguageModel.suffix_verify_kwargs()` — gemma4
  returns `{}`, qwen3_5 returns `{"capture_layer_ids": []}` (creates the `gdn_sink` + enables
  `target_verify`, capturing GDN snapshots). `run_suffix_decoding_rounds` reads the hook (never
  sniffs model_type) and threads `**verify_kwargs` into the verify forward; the existing
  `rollback_speculative_cache` now receives non-None `gdn_states` on qwen.
- The §8 caveat about empty `capture_layer_ids=[]` adding hidden-capture overhead is resolved:
  confirmed no overhead — the empty list leaves `capture_set` empty → `hidden_states == []`.
- Follow-up bug found only on the real model (not the tiny tests): the `target_verify` attention
  path's manual per-position loop slices cache keys directly, which crashes under quantized KV
  (Qwen3.6 runs `kv_quant_scheme=turboquant`) with `'_QuantizedStateProxy' object is not
  subscriptable`. Fixed by skipping the manual loop for quantized caches (`hasattr(cache,
  "bits")`) and falling through to the cache-aware SDPA path — same result up to FP; also fixes
  dflash/mtp target-verify under quantized KV.
- Tests (all green; 41 suffix + 144 speculative): tiny qwen3_5 GDN rollback equivalence gate, a
  targeted GDN-state-restored-to-clean assertion, a turboquant-KV regression test, hook unit
  guards, and a natural-proposer greedy-equivalence gate. gemma4 v1 gates unaffected.
- Enabled `draft_kind: suffix` on all three `Qwen3.6-27B*` entries in `main_models.yaml`.
- Real-model validation on Qwen3.6-27B-UD-MLX-6bit: correct (no crash, coherent output on
  turboquant + GDN) and ~2.79× decode speedup on echo-heavy code (27.4 vs 9.8 tok/s baseline),
  no regression on novel prose (graceful degradation).

### The gap (verified in code)

v1's suffix verify does `lm(verify_input, cache=prompt_cache)` with no capture flag. In
`models/qwen3_5/language.py`, `gdn_states` is only populated when the forward receives
`capture_layer_ids` — that creates a `gdn_sink` list and sets `target_verify=True`
(`LanguageModel.__call__` ~line 2387; `gdn_sink = [] if capture_layer_ids is not None else None`
~lines 2512-2515; `gdn_states=gdn_sink` ~line 2542). Without the flag, `gdn_states` is `None`
and the GatedDeltaNet layers update their recurrent state *in-place* across the verify block. So
on a rejected draft, `rollback_speculative_cache(prompt_cache, gdn_states=None, accepted, bs)`
cannot restore the GDN state → corrupted output. (gemma4 has no GDN, so its `gdn_states` is
always None and its rollback trims KV only — correct as-is.)

### The fix (reuses existing machinery — no training, no new rollback logic)

1. Add a per-target capability hook so suffix verify requests exactly the rollback state the
   model needs — a method on the LM returning the verify-forward kwargs: gemma4 → `{}`
   (KV-only); qwen3_5 → `{"capture_layer_ids": []}` (empty list still creates the `gdn_sink`
   and enables `target_verify` mode, capturing GDN snapshots without drafter hidden states).
   Detect via the hook/method, NOT model_type sniffing. Default `{}` for unknown models.
2. Suffix verify becomes `verify_out = lm(verify_input, cache=prompt_cache, **verify_kwargs)`;
   pass `verify_out.gdn_states` to `rollback_speculative_cache`. The rounds already do
   `getattr(verify_out, "gdn_states", None)`, which becomes non-None for qwen.
3. The existing `qwen3_5.rollback_speculative_cache` (~line 1932) already consumes `gdn_states`
   (it's what MTP and dflash use) — no new rollback code.
4. Reference to mirror: `speculative/dflash.py::_dflash_rounds` verify on qwen —
   `lm(verify_input, cache=prompt_cache, capture_layer_ids=...)` then
   `rollback_speculative_cache(prompt_cache, verify_out.gdn_states, accepted, bs)`. Suffix
   mirrors this minus the drafter-hidden consumption (suffix has no drafter).

### Caveats / things to verify in v1.1

- Empty `capture_layer_ids=[]` may still append a trailing hidden state (minor overhead) —
  confirm and, if it matters, add a gdn-only capture flag. (Resolved: no overhead — see Outcome.)
- Suffix must keep working under quantized KV (Qwen3.6 runs `kv_quant_scheme: turboquant`,
  `kv_bits=3`). dflash/MTP already handle TQ caches on qwen — reuse, add no kv_bits gating.
  (Shipped: hit a target_verify crash under turboquant; fixed — see Outcome.)
- Correctness gate unchanged and non-negotiable: greedy output token-identical with/without
  suffix, up to floating-point non-associativity (see §9: block-vs-single matmul already
  diverges on soft distributions; inherent to all block-verify speculation, not a suffix bug).

### v1.1 steps

a. Add the verify-kwargs hook to gemma4 (`{}`) and qwen3_5 (gdn-capture).
b. Thread it through `run_suffix_decoding_rounds`.
c. tiny-qwen3_5 tests: greedy equivalence + a forced-draft test asserting GDN state is restored
   on rejection (mirror the gemma4 rollback gate that checks cache offset).
d. Enable suffix on the `Qwen3.6-27B*` entries in `main_models.yaml`.
e. Benchmark on Qwen3.6.

---

## 9. v1 implementation notes

- **Greedy is token-identical up to FP non-associativity** (block-vs-single matmul). Exact on
  peaked/echo distributions; can flip on low-confidence tokens. Inherent to block-verify
  speculation — the existing mtp/dflash paths share it.
- **Adaptive draft sizing** (linear ramp-up / geometric backoff) plus a chunked pure-async
  miss-decode path. Keeps novel-prose from regressing vs baseline; residual ~10% is inherent
  host-readback for the n-gram lookup.
- **`draft_cooldown=N`** (CLI `--draft-cooldown`, YAML `draft_cooldown`): after N consecutive
  0-accept verify rounds, suppress proposing for a geometric window, then probe. Avoids wasted
  verifies on novel text.
- **Server integration.** Suffix runs on the OWUI cached single-chat path (B==1, via
  `generate_step`); non-cached/batch requests fall back to plain decode. It honors
  `thinking_budget` (forces the model's real end-of-thinking token at the cap, block
  granularity) and falls back to plain decode for `response_format` (structured output, which
  an n-gram drafter can't satisfy anyway). `thinking_budget` now also defaults+caps to
  0.8×max_tokens server-wide, and the old `THINKING_TRUNCATION_MSG` placeholder was removed.

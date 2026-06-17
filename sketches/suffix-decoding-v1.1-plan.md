# SuffixDecoding v1.1 — Hybrid GatedDeltaNet (Qwen3.6 / qwen3_5) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make drafter-free SuffixDecoding produce greedy-token-identical output on Qwen3.6 / qwen3_5 (GatedDeltaNet) by capturing the recurrent GDN state during the speculative verify forward so a rejected draft can be rolled back.

**Architecture:** Add a per-target capability hook (`suffix_verify_kwargs`) on each model's `LanguageModel` that returns the verify-forward kwargs needed to capture rollback state — `{}` for KV-only gemma4, `{"capture_layer_ids": []}` for qwen3_5 (which builds a `gdn_sink` + enables target-verify, capturing per-position GDN snapshots with *zero* hidden-state overhead). Thread that hook into `run_suffix_decoding_rounds` so the existing `rollback_speculative_cache` receives non-None `gdn_states` on qwen. No training, no new rollback logic, no new dispatch — reuse the machinery dflash/mtp already use.

**Tech Stack:** Python, MLX / mlx_vlm fork, pytest. Apple-silicon Metal (GDN kernels).

## Global Constraints

- **Edit the canonical forks, NOT the submodules.** All code changes go in `../mlx-vlm` (the parent-folder fork). Do **not** edit `mlx_local_stack/src/*`. (Memory: edit-parent-forks-not-submodules.)
- **The only file outside `../mlx-vlm`** is the post-approval enablement of `mlx_local_stack/main_models.yaml` (Task 6, gated on review).
- **Test runner (confirmed working, v1 = 32/32 green in 1.45s):**
  ```bash
  PYTHONPATH=../mlx-vlm \
    uv run --with pytest --project $STACK_REPO \
    pytest ../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py -q
  ```
  The `PYTHONPATH=.../mlx-vlm` prefix forces `import mlx_vlm` to resolve to the fork; `--project <mlx_local_stack>` reuses the stack's uv env without mutating it.
- **Correctness bar (non-negotiable):** under greedy sampling, suffix output is token-identical with and without suffix decoding, up to floating-point non-associativity (block-vs-single matmul; inherent to all block-verify speculation — see sketch §9). Token-identical is the gate.
- **Do not touch the mtp / dflash / eagle3 paths.** Only the suffix path (`speculative/suffix_decoding.py`) + the two new model hooks.
- **No `kv_bits` gating.** Qwen3.6 runs `kv_quant_scheme: turboquant, kv_bits=3`; the rollback is cache-type agnostic (`c.is_trimmable()` / `c.trim()`), and dflash/mtp already handle TQ caches on qwen. Add no quantization-specific branches.
- **Do NOT commit or push without explicit approval.** Each task ends with a commit *only after its tests are green*; the whole branch stops for review before Task 6 (sketch §8 step d). An approved plan does not cover newly found bugs — surface them. (Memory: propose-before-fixing.)

---

## Verified seam (anchors checked against current code, 2026-06-16)

- `speculative/suffix_decoding.py:352` — the gap: `verify_out = lm(verify_input, cache=prompt_cache)` with **no** capture flag → `gdn_states` is None on qwen.
- `speculative/suffix_decoding.py:372-377` — rollback already passes `getattr(verify_out, "gdn_states", None)`; becomes non-None for qwen once the hook fires.
- `models/qwen3_5/language.py:2400` `capture_layer_ids = kwargs.pop("capture_layer_ids", None)`; `:2514` `gdn_sink = [] if capture_layer_ids is not None else None`; `:2515` `target_verify = gdn_sink is not None`; `:2542` `gdn_states=gdn_sink`; `:1901` `capture_set = set(capture_layer_ids) if capture_layer_ids else set()` (empty list → no hidden capture); `:1932` `def rollback_speculative_cache(...)` (consumes `gdn_states`).
- `models/gemma4/language.py:711` `__call__(... capture_layer_ids=None ...)`; `:751` `def rollback_speculative_cache(...)` (`del gdn_states`; KV-only).
- `speculative/dflash.py:127-131` + `:155-157` — the reference: qwen verify with `capture_layer_ids=target_layer_ids` then `rollback_speculative_cache(prompt_cache, verify_out.gdn_states, accepted, bs)`. Suffix mirrors this minus the drafter-hidden consumption.
- **Empirically confirmed (throwaway scripts, now removed):**
  - `capture_layer_ids=[]` on a real tiny qwen3_5 → `gdn_states` length 1 (one GDN layer captured), `hidden_states == []` (no hidden-capture overhead). Resolves the §8 caveat: an empty list adds **no** trailing hidden state.
  - Current code RED is deterministic: a forcing-draft suffix run on qwen raises `TypeError: 'NoneType' object is not iterable` in `rollback_speculative_cache` (line 2008 iterates `gdn_states=None`) on the first rejection.
  - A tiny qwen3_5 needs **large enough GDN dims** or the GDN decode-step Metal kernel fails to build (`zero-length arrays … float state[n_per_t]`). Working config: `hidden_size=64, linear_key_head_dim=linear_value_head_dim=32, linear_num_key_heads=linear_num_value_heads=4, num_attention_heads=4, num_key_value_heads=2, head_dim=16`. (4/4-dim configs crash.)
  - A tiny qwen3_5 `LanguageModel` needs a minimal `ModelConfig` attached (`get_rope_index` reads `self.config.vision_config.spatial_merge_size`), exactly as `test_speculative.py:860`.
  - `ArraysCache.state` (the GDN slot) is `[conv (1,3,384), recurrent (1,4,32,32)]` — `mx.allclose` these for the restore assertion.

---

## File Structure

- **Modify** `../mlx-vlm/mlx_vlm/speculative/suffix_decoding.py` — read the hook once, pass `**verify_kwargs` to the verify forward. (~4 lines added, 1 line changed.)
- **Modify** `../mlx-vlm/mlx_vlm/models/gemma4/language.py` — add `LanguageModel.suffix_verify_kwargs(self) -> dict` returning `{}`.
- **Modify** `../mlx-vlm/mlx_vlm/models/qwen3_5/language.py` — add `LanguageModel.suffix_verify_kwargs(self) -> dict` returning `{"capture_layer_ids": []}`.
- **Modify** `../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py` — add the qwen3_5 GDN tests (helper, RED gate, unit guards, equivalence gate). Keep all 32 v1 tests untouched and green.
- **Modify (Task 6, post-approval only)** `mlx_local_stack/main_models.yaml` — enable suffix on the `Qwen3.6-27B*` entries.

---

### Task 1: tiny-qwen3_5 GDN rollback gate — write the failing test FIRST

This is the headline TDD step: an equivalence test that is *guaranteed* to exercise the GDN rollback path (forcing proposer → rejection every round) and therefore fails on current code.

**Files:**
- Test: `../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py` (append a new section)

**Interfaces:**
- Consumes: `run_suffix_decoding_rounds`, `SuffixDecodingProposer` (already imported at top of the test file); `mlx_vlm.models.qwen3_5.language` as `qwen_language`; `mlx_vlm.models.cache` as `cache_mod`; `ArraysCache` from `mlx_vlm.models.cache`.
- Produces: `_tiny_qwen3_5(seed)` helper and `_gdn_state(cache)` reader reused by Tasks 3–5.

- [ ] **Step 1: Add the qwen3_5 test harness + the forcing-draft rollback gate**

Append to `test_suffix_decoding.py`:

```python
# --------------------------------------------------------------------------- #
# Integration — hybrid GatedDeltaNet (qwen3_5) GDN-state rollback
# --------------------------------------------------------------------------- #
import mlx_vlm.models.qwen3_5.language as qwen_language  # noqa: E402
from mlx_vlm.models.cache import ArraysCache  # noqa: E402


def _tiny_qwen3_5(seed=0):
    # Dims chosen so the GatedDeltaNet decode-step Metal kernel builds: 4/4-dim
    # configs hit "zero-length arrays (float state[n_per_t])". num_hidden_layers=2
    # + full_attention_interval=2 => layer 0 is GDN (ArraysCache), layer 1 is full
    # attention (KVCache), so the recurrent-state rollback path is actually exercised.
    mx.random.seed(seed)
    cfg = qwen_language.TextConfig(
        model_type="qwen3_5_text",
        hidden_size=64,
        intermediate_size=128,
        linear_num_value_heads=4,
        linear_num_key_heads=4,
        linear_key_head_dim=32,
        linear_value_head_dim=32,
        linear_conv_kernel_dim=4,
        num_hidden_layers=2,
        full_attention_interval=2,
        num_attention_heads=4,
        rms_norm_eps=1e-6,
        vocab_size=32,
        num_key_value_heads=2,
        max_position_embeddings=128,
        tie_word_embeddings=True,
        head_dim=16,
        rope_parameters={
            "type": "default",
            "mrope_section": [1, 0, 0],
            "rope_theta": 10000,
            "partial_rotary_factor": 0.25,
        },
    )
    lm = qwen_language.LanguageModel(cfg)
    # get_rope_index reads self.config.vision_config.spatial_merge_size even for
    # text-only input, so attach a minimal ModelConfig (mirrors test_speculative.py).
    lm.config = qwen_language.ModelConfig(
        text_config=cfg,
        vision_config=SimpleNamespace(spatial_merge_size=2),
        model_type="qwen3_5",
        image_token_id=101,
        video_token_id=102,
        image_token_index=101,
        video_token_index=102,
        vision_start_token_id=100,
        vision_end_token_id=103,
        vocab_size=32,
    )
    lm.eval()
    return lm


def _qwen_reference_greedy(lm, prompt, n_tokens):
    c = cache_mod.make_prompt_cache(lm)
    out = lm(mx.array([prompt]), cache=c)
    tok = int(mx.argmax(out.logits[:, -1, :], axis=-1).item())
    toks = [tok]
    for _ in range(n_tokens - 1):
        o = lm(mx.array([[tok]]), cache=c)
        tok = int(mx.argmax(o.logits[:, -1, :], axis=-1).item())
        toks.append(tok)
    return toks, c


def _gdn_state(cache):
    """Flattened GDN recurrent + conv arrays from the ArraysCache slots."""
    arrs = []
    for c in cache:
        if isinstance(c, ArraysCache):
            arrs.extend(s for s in c.state if s is not None)
    return arrs


def test_suffix_decoding_rollback_preserves_gdn_on_real_tiny_qwen3_5():
    # Forces a verified draft every round so the GDN recurrent state advances
    # through rejected draft positions and MUST be restored on rollback. Without
    # capture (gdn_states=None) the qwen rollback cannot restore it -> divergence
    # (in fact a TypeError on current code). With capture, output stays exactly
    # greedy AND the GDN state matches a clean autoregressive decode.
    lm = _tiny_qwen3_5(seed=2)
    model = SimpleNamespace(language_model=lm)
    prompt = [3, 4, 5, 6, 7, 8, 9, 10]
    n = 20

    ref, ref_cache = _qwen_reference_greedy(lm, prompt, n)

    proposer = _ForcingProposer([3, 4, 5])  # unlikely to match random greedy
    spec_cache = cache_mod.make_prompt_cache(lm)
    out = lm(mx.array([prompt]), cache=spec_cache)
    first_bonus = int(mx.argmax(out.logits[:, -1, :], axis=-1).item())
    spec = [first_bonus] + [
        tok
        for tok, _ in run_suffix_decoding_rounds(
            model,
            proposer,
            spec_cache,
            prompt,
            first_bonus=first_bonus,
            max_tokens=n,
            sampler=_ARGMAX,
            draft_block_size=8,
        )
    ]

    assert spec == ref
    assert proposer.accept_lens  # the forcing draft was verified every round
    # KV cache tracks the clean AR cache to within one (final, un-rolled-back) block.
    assert _cache_offset(spec_cache) - _cache_offset(ref_cache) <= 8
    # GDN recurrent + conv state was restored to the clean-decode reference.
    spec_gdn, ref_gdn = _gdn_state(spec_cache), _gdn_state(ref_cache)
    assert len(spec_gdn) == len(ref_gdn) and spec_gdn
    for a, b in zip(spec_gdn, ref_gdn):
        assert bool(mx.allclose(a, b, atol=1e-4).item())
```

(`_ForcingProposer`, `_cache_offset`, `_ARGMAX`, and `SimpleNamespace`/`cache_mod` are already defined/imported in this test file from v1.)

- [ ] **Step 2: Run the test and confirm it FAILS on current code**

Run:
```bash
PYTHONPATH=../mlx-vlm \
  uv run --with pytest --project $STACK_REPO \
  pytest ../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py::test_suffix_decoding_rollback_preserves_gdn_on_real_tiny_qwen3_5 -q
```
Expected: **FAIL** — `TypeError: 'NoneType' object is not iterable` raised inside `rollback_speculative_cache` (the verify forward captured no `gdn_states`). This pins the v1.1 gap.

- [ ] **Step 3: Do not commit yet** — the test is red by design; it goes green in Task 2.

---

### Task 2: Implement the capture hook + thread it through suffix verify (turn Task 1 green)

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/models/gemma4/language.py` (above `rollback_speculative_cache`, ~line 751)
- Modify: `../mlx-vlm/mlx_vlm/models/qwen3_5/language.py` (above `rollback_speculative_cache`, ~line 1932)
- Modify: `../mlx-vlm/mlx_vlm/speculative/suffix_decoding.py` (after the rollback-capability check, ~line 250; verify call at ~line 352)

**Interfaces:**
- Produces: `LanguageModel.suffix_verify_kwargs(self) -> dict` on both models; `run_suffix_decoding_rounds` now reads it and forwards `**verify_kwargs` to the verify forward.

- [ ] **Step 1: Add the hook to gemma4** (insert immediately above `def rollback_speculative_cache(` at `models/gemma4/language.py:751`)

```python
    def suffix_verify_kwargs(self) -> dict:
        """Extra kwargs for the SuffixDecoding verify forward (rollback capture).

        Gemma 4 is KV-only (no SSM/GatedDeltaNet recurrent state), so the verify
        needs no capture flag — ``rollback_speculative_cache`` trims KV alone.
        """
        return {}
```

- [ ] **Step 2: Add the hook to qwen3_5** (insert immediately above `def rollback_speculative_cache(` at `models/qwen3_5/language.py:1932`)

```python
    def suffix_verify_kwargs(self) -> dict:
        """Extra kwargs for the SuffixDecoding verify forward (rollback capture).

        qwen3_5 has GatedDeltaNet recurrent layers whose state advances in-place
        across the verify block. ``capture_layer_ids=[]`` makes ``__call__`` build
        a ``gdn_sink`` (and enable target-verify), capturing per-position GDN
        snapshots for ``rollback_speculative_cache``. The empty list leaves
        ``capture_set`` empty, so no hidden states are captured — same idiom as
        ``speculative_verify_logits``/``speculative_verify_hidden``.
        """
        return {"capture_layer_ids": []}
```

- [ ] **Step 3: Read the hook once in the rounds loop** (in `speculative/suffix_decoding.py`, insert right after the `raise RuntimeError(...)` block that ends at ~line 250, before `proposer.reset(prompt_token_ids)`)

```python
    # Per-target capture hook: dense KV-only models (gemma4) need nothing; hybrid
    # GatedDeltaNet models (qwen3_5) return {"capture_layer_ids": []} so the verify
    # forward snapshots GDN state for rollback. Detected via the hook, never by
    # model_type; defaults to no extra kwargs (e.g. fake LMs in tests).
    _vk_hook = getattr(lm, "suffix_verify_kwargs", None)
    verify_kwargs = _vk_hook() if callable(_vk_hook) else {}
```

- [ ] **Step 4: Pass the kwargs to the verify forward** (in `speculative/suffix_decoding.py`, the main verify at ~line 352)

Replace:
```python
            verify_out = lm(verify_input, cache=prompt_cache)
```
with:
```python
            verify_out = lm(verify_input, cache=prompt_cache, **verify_kwargs)
```
(Leave the thinking-budget single-token forward at ~line 278 and the miss-path forward at ~line 311 unchanged — they are committed, baseline-equivalent decodes that are never rolled back, so they need no GDN capture, exactly as dflash captures only on the speculative verify.)

- [ ] **Step 5: Run the Task 1 gate and confirm it PASSES**

Run:
```bash
PYTHONPATH=../mlx-vlm \
  uv run --with pytest --project $STACK_REPO \
  pytest ../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py::test_suffix_decoding_rollback_preserves_gdn_on_real_tiny_qwen3_5 -q
```
Expected: **PASS** (`spec == ref`, cache-offset bound holds, GDN state allclose).

- [ ] **Step 6: Commit**

```bash
cd ../mlx-vlm
git add mlx_vlm/models/gemma4/language.py mlx_vlm/models/qwen3_5/language.py \
        mlx_vlm/speculative/suffix_decoding.py mlx_vlm/tests/test_suffix_decoding.py
git commit -m "feat(suffix): capture GDN state on qwen3_5 verify for rollback (v1.1)"
```
(Write the message from `git diff --staged`. Memory: verify-staged-before-commit. Do not push.)

---

### Task 3: Unit guard — the hook returns the right kwargs per model

**Files:**
- Test: `../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py`

- [ ] **Step 1: Write the unit test**

```python
def test_suffix_verify_kwargs_hook_per_model():
    # gemma4: KV-only -> no capture kwargs.
    assert _tiny_gemma4(seed=0).suffix_verify_kwargs() == {}
    # qwen3_5: GDN -> capture_layer_ids=[] (gdn_sink without hidden capture).
    assert _tiny_qwen3_5(seed=0).suffix_verify_kwargs() == {"capture_layer_ids": []}
```

- [ ] **Step 2: Run it and confirm PASS**

Run:
```bash
PYTHONPATH=../mlx-vlm \
  uv run --with pytest --project $STACK_REPO \
  pytest ../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py::test_suffix_verify_kwargs_hook_per_model -q
```
Expected: **PASS**.

- [ ] **Step 3: Commit**

```bash
cd ../mlx-vlm
git add mlx_vlm/tests/test_suffix_decoding.py
git commit -m "test(suffix): unit-guard suffix_verify_kwargs per model"
```

---

### Task 4: Unit guards — kwargs reach the verify forward + GDN capture is load-bearing

This is the mutation check the spec requires ("confirm a disabled/None gdn_states FAILS the test"), split into two deterministic, model-light assertions.

**Files:**
- Test: `../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py`

- [ ] **Step 1: Write the threading test (fake LM records kwargs)**

```python
class _KwargRecordingLM:
    """Fake LM exposing a suffix_verify_kwargs hook; records what the verify
    forward actually received so we can prove the kwargs are threaded through."""

    def __init__(self, nxt, kwargs, vocab=128):
        self._nxt = nxt
        self._kwargs = dict(kwargs)
        self.vocab = vocab
        self.verify_kwargs_seen = None

    def suffix_verify_kwargs(self):
        return dict(self._kwargs)

    def __call__(self, inputs, cache=None, **kwargs):
        ids = [int(x) for x in inputs.reshape(-1).tolist()]
        if len(ids) > 1:  # the multi-token verify forward (not the 1-token miss path)
            self.verify_kwargs_seen = kwargs
        rows = []
        for x in ids:
            row = [0.0] * self.vocab
            row[self._nxt[x]] = 10.0
            rows.append(row)
        return SimpleNamespace(logits=mx.array([rows]), gdn_states=None)

    def rollback_speculative_cache(self, caches, gdn_states, accepted, block_size):
        pass


def test_suffix_verify_forward_receives_hook_kwargs():
    nxt = {0: 1, 1: 2, 2: 3, 3: 4, 7: 50}
    lm = _KwargRecordingLM(nxt, {"capture_layer_ids": []})
    model = SimpleNamespace(language_model=lm)
    _drive(model, _ScriptedProposer([[1, 2, 7]]), first_bonus=0, max_tokens=5)
    assert lm.verify_kwargs_seen == {"capture_layer_ids": []}


def test_suffix_no_hook_passes_no_extra_kwargs():
    # A fake LM without the hook (the v1 fakes) must see an unchanged verify call.
    nxt = {0: 1, 1: 2, 2: 3, 3: 4, 7: 50}

    class _NoHookLM(_KwargRecordingLM):
        suffix_verify_kwargs = None  # attribute is not callable -> default {}

    lm = _NoHookLM(nxt, {})
    model = SimpleNamespace(language_model=lm)
    _drive(model, _ScriptedProposer([[1, 2, 7]]), first_bonus=0, max_tokens=5)
    assert lm.verify_kwargs_seen == {}
```

- [ ] **Step 2: Write the load-bearing test (capture flag is what populates gdn_states)**

```python
def test_qwen_capture_layer_ids_is_load_bearing_for_gdn_states():
    # Direct proof that the hook's kwarg — not the model by itself — is what makes
    # gdn_states non-None. A disabled/None capture leaves rollback nothing to restore.
    lm = _tiny_qwen3_5(seed=0)
    c = cache_mod.make_prompt_cache(lm)
    lm(mx.array([[3, 4, 5]]), cache=c)

    plain = lm(mx.array([[6, 7, 8]]), cache=c)
    assert plain.gdn_states is None  # without capture: nothing to roll back

    c2 = cache_mod.make_prompt_cache(lm)
    lm(mx.array([[3, 4, 5]]), cache=c2)
    captured = lm(mx.array([[6, 7, 8]]), cache=c2, **lm.suffix_verify_kwargs())
    assert captured.gdn_states is not None and len(captured.gdn_states) >= 1
    assert captured.hidden_states == []  # capture_layer_ids=[] adds no hidden overhead
```

- [ ] **Step 3: Run both and confirm PASS**

Run:
```bash
PYTHONPATH=../mlx-vlm \
  uv run --with pytest --project $STACK_REPO \
  pytest ../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py \
    -k "receives_hook_kwargs or no_hook_passes or load_bearing" -q
```
Expected: **PASS** (3 tests).

- [ ] **Step 4: Commit**

```bash
cd ../mlx-vlm
git add mlx_vlm/tests/test_suffix_decoding.py
git commit -m "test(suffix): guard kwargs threading + GDN-capture load-bearing"
```

---

### Task 5: Natural-proposer equivalence gate + full regression

**Files:**
- Test: `../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py`

- [ ] **Step 1: Write the natural-proposer equivalence test (mirrors the gemma4 gate)**

```python
def test_suffix_decoding_matches_greedy_on_real_tiny_qwen3_5():
    # THE GATE on hybrid GDN: greedy output token-identical with/without suffix,
    # using the real SuffixDecodingProposer (mixed accept/reject) on a repetitive
    # prompt, exercising the real verify, KV + GDN caches, and rollback.
    lm = _tiny_qwen3_5(seed=0)
    model = SimpleNamespace(language_model=lm)
    prompt = [3, 4, 5, 6, 7, 8] * 4
    n = 24

    ref, _ = _qwen_reference_greedy(lm, prompt, n)

    proposer = SuffixDecodingProposer(min_match=2)
    spec_cache = cache_mod.make_prompt_cache(lm)
    out = lm(mx.array([prompt]), cache=spec_cache)
    first_bonus = int(mx.argmax(out.logits[:, -1, :], axis=-1).item())
    spec = [first_bonus] + [
        tok
        for tok, _ in run_suffix_decoding_rounds(
            model,
            proposer,
            spec_cache,
            prompt,
            first_bonus=first_bonus,
            max_tokens=n,
            sampler=_ARGMAX,
            draft_block_size=8,
        )
    ]

    assert spec == ref
    assert len(spec) == n
```

- [ ] **Step 2: Run the whole suffix suite (new qwen tests + all 32 v1 tests)**

Run:
```bash
PYTHONPATH=../mlx-vlm \
  uv run --with pytest --project $STACK_REPO \
  pytest ../mlx-vlm/mlx_vlm/tests/test_suffix_decoding.py -q
```
Expected: **all PASS** (32 v1 + the new qwen tests). The v1 gemma4 tests must stay green — the gemma4 hook returns `{}`, so its verify call is unchanged.

- [ ] **Step 3: Run the broader speculative suite (no collateral regressions)**

Run:
```bash
PYTHONPATH=../mlx-vlm \
  uv run --with pytest --project $STACK_REPO \
  pytest ../mlx-vlm/mlx_vlm/tests/test_speculative.py -q
```
Expected: **all PASS** (mtp/dflash/eagle3 paths untouched).

- [ ] **Step 4: Commit**

```bash
cd ../mlx-vlm
git add mlx_vlm/tests/test_suffix_decoding.py
git commit -m "test(suffix): greedy-equivalence gate on tiny qwen3_5 (GDN)"
```

---

## REVIEW CHECKPOINT (mandatory stop — sketch §8 step d)

Before Task 6, **stop and present for review**:
- `git -C ../mlx-vlm diff <base>..HEAD` (the full v1.1 diff).
- The tiny-qwen test results from Task 5 Steps 2–3.
- Confirmation that the RED (Task 1 Step 2) → GREEN (Task 2 Step 5) transition happened.

Do **not** proceed to Task 6, do not push, until the user approves.

---

### Task 6: Enable suffix on Qwen3.6-27B + benchmark (POST-APPROVAL ONLY)

**Files:**
- Modify: `mlx_local_stack/main_models.yaml` (the `Qwen3.6-27B*` entries)

- [ ] **Step 1: Verify the server actually wires `draft_kind=suffix` through to qwen.** Grep `main_models.yaml` for how gemma4 entries enable suffix today and confirm mlx-serve forwards it (v1 already wired the OWUI single-chat path per sketch §9). If a mlx-serve change is needed, surface it as a new proposal — it is out of this plan's approved scope.
- [ ] **Step 2: Mirror the gemma4 suffix config onto the `Qwen3.6-27B*` entries** in `main_models.yaml`. Keep `kv_quant_scheme: turboquant, kv_bits=3` as-is (no kv_bits gating).
- [ ] **Step 3: Benchmark** on a coding-echo prompt and a novel-prose prompt via `benchmark/` (decode tok/s with/without suffix). Expect a gain on echo, no regression on novel (graceful degradation). Acceptance per sketch §7.
- [ ] **Step 4: Sync submodules** from the forks per the repo's normal flow, then commit the YAML.

---

## Self-Review

- **Spec coverage (sketch §8):** (1) per-target hook gemma4 `{}` / qwen `{"capture_layer_ids": []}` → Tasks 2–3. (2) verify becomes `lm(..., **verify_kwargs)`, rollback gets non-None `gdn_states` → Task 2. (3) reuse existing qwen `rollback_speculative_cache` → no rollback code written (Task 2). (4) mirror dflash minus drafter-hidden → Task 2 Step 4 leaves the empty-list path. §8 caveats: empty-list overhead → **empirically resolved** (`hidden_states == []`, Task 4 Step 2); TQ caches → Global Constraints (no gating); correctness bar → Tasks 1 & 5. §8 steps a–e → Tasks 2,2,1+4,6,6.
- **Constraints met:** edits in `../mlx-vlm` only (Tasks 1–5); mtp/dflash/eagle3 untouched; detection via hook not model_type; no commit/push without approval; review checkpoint before enablement.
- **Placeholder scan:** every code step has complete code; every run step has an exact command + expected result. No TODOs.
- **Type consistency:** `suffix_verify_kwargs(self) -> dict` identical on both models and read identically in `run_suffix_decoding_rounds`; helpers `_tiny_qwen3_5`, `_qwen_reference_greedy`, `_gdn_state` defined in Task 1 and reused by Tasks 3–5; reuses existing `_ForcingProposer`, `_ScriptedProposer`, `_drive`, `_cache_offset`, `_ARGMAX`, `_tiny_gemma4` from v1.
- **Risk note:** the GREEN side of Tasks 1/5 (token-identical + GDN allclose after the fix) is high-confidence by construction (identical machinery to the tested dflash path) but is only *proven* when the tests run during execution; the RED is already empirically confirmed.
```

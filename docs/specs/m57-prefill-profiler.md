# M57 step 2 — env-gated prefill component profiler in the fork (spec, 2026-10-04)

Approved C111. Purpose: attribute served prefill time per chunk to components. Step-1 evidence
(`docs/proposal-flash-attention.md`, E1–E10) left about a third of the context-proportional prefill cost unattributed.
Diagnostic only: no behaviour change when the switch is unset.

## Deliverable

- Parent fork `../mlx-vlm`, branch `m57-prefill-profile` from `main`. Fork only; no stack change, no submodule bump, no push.
- New module `mlx_vlm/prefill_profile.py`. Reuse `_PhaseTimer` from `mlx_vlm/speculative/mtp_profile.py` if it imports without
  a cycle; otherwise copy the minimum. Same conventions as that module: a phase mark is `mx.eval(outputs)` then
  `mx.synchronize()` then a timestamp; reporting never raises.
- Switch: `MLX_VLM_PREFILL_PROFILE=1`. Unset → the profiler object is `None` and every hook is a single `is not None` check:
  no added `mx.eval`, no `mx.synchronize`, no timers, one env lookup per generation.
- Scope: the single-sequence chunked prefill loop in `mlx_vlm/generate/ar.py` (the loop that calls `model.language_model` per
  chunk) and the `qwen3_5` language model. Other model families: hooks absent, profiler reports only chunk-level phases.
- Active-profiler handle: set by the chunk loop for the duration of one chunk, cleared in `finally`. Layer code reads it through
  `prefill_profile.active()`. Document it as single-request diagnostic state; it must be `None` outside a profiled chunk.

## Phases (per chunk)

| phase | where | covers |
|---|---|---|
| `attn_prep` | `Qwen3_5Attention` | q/k/v projections, norms, rotary — everything in `_prepare_projected_qkv` before the cache update |
| `kv_update` | `Qwen3_5Attention` | `cache.update_and_fetch` (and any preallocation it triggers) |
| `sdpa` | `Qwen3_5Attention` | the `scaled_dot_product_attention` call only |
| `attn_out` | `Qwen3_5Attention` | gate, transpose/reshape, `o_proj` |
| `gdn` | `Qwen3_5DecoderLayer` | the whole `linear_attn` call |
| `mlp` | `Qwen3_5DecoderLayer` | residual add, post-norm, `mlp` (both layer kinds) |
| `cache_post` | chunk loop | `quantize_cache_fn`, `preallocate_cache_fn`, `mx.eval([c.state ...])`, eviction hook |
| `clear_cache` | chunk loop | `mx.clear_cache()` |
| `other` | chunk loop | chunk wall minus the sum of the above (embedding, final norm, Python, snapshot handling) |

If `_prepare_projected_qkv` cannot be split without changing its behaviour, time it as one phase `attn_prep_kv` and say so in the
commit message. Do not restructure model code to make a phase boundary.

Per chunk also record: tokens in the chunk, key length after the chunk (cumulative offset).

## Report

One stderr line every 32 chunks and one final line per generation, values are means over the window:

`[prefill_profile] chunks=<n> tokens=<n> keys=<key length at window end> wall=<ms/chunk> sdpa=<ms/chunk> kv_update=… attn_prep=… attn_out=… gdn=… mlp=… cache_post=… clear_cache=… other=… final=<0|1>`

## Tests (`mlx_vlm/tests/test_prefill_profile.py`, CPU-pinned, tiny fake model — no real checkpoint, no GPU)

Write each test first and watch it fail.

1. Switch unset: profiler code calls `mx.synchronize` zero times (monkeypatch counter), emits no line, `active()` is `None`.
2. Switch set: a 3-chunk run emits window/final lines with every field; `chunks` and `tokens` are exact; every phase ≥ 0;
   `other` ≥ 0 within timer tolerance.
3. Outputs (logits and cache state) with the switch set equal outputs with it unset, exactly, on CPU.
4. A raising profiler (monkeypatched `mark`) does not break generation and clears the active handle.
5. `active()` is `None` after a profiled generation and after an exception inside a chunk.

## Rules

- Minimal hunks in upstream-owned files, each marked `# Fork:`. black, line length 88.
- No real model loads, no Metal workloads, no servers. Run only the new tests and the existing
  `mlx_vlm/tests/test_mtp_profile.py`.
- Commit on the branch. Do not push. Report: files changed, test output, any phase that could not be separated.

## Run (operator session, after cold review; server path only)

- Lean router with `PYTHONPATH=<parent fork>` and `MLX_VLM_PREFILL_PROFILE=1` in its environment, overlays
  `$STACK_WORKDIR/m57/overlays/step512.yaml` and `step1024.yaml`, one 64K and one 128K cold prompt each. Read
  `[prefill_profile]` lines from `$TMPDIR/mlx-manager-logs/<model>.log`.
- Rows from profiled runs go to `$STACK_WORKDIR/m57/` only — the worker serves the branch, not the pinned submodule, and the eval
  fences perturb timing; nothing from these runs enters `benchmark/results/`.

## Pre-registered reading

- The largest context-proportional phase other than `sdpa` is fixed first, losslessly, inside M57.
- Per-token `gdn + mlp + attn_prep + attn_out` falling ≥ 10 % from step 512 to 1024 puts chunk size into the M57 recipe.
- Fused `sdpa` ≥ 40 % of the 128K chunk wall after those fixes funds the pinned-commit kernel comparison (P54 / X10).
- Profiled wall more than 25 % above the unprofiled wall for the same prompt: report shares only, not absolute times.

## Amendment 1 (2026-10-04, after two cold reviews of `924e5c3f` — a Claude reviewer and Codex `gpt-6-astra` — both FIX-THEN-SHIP)

Binding; where it conflicts with the text above, this wins.

1. **Profile only the work production prefill does.** The chunk loop discards the chunk output; production evaluates cache state
   only. Never pass the chunk output (or logits) to a mark. The TERMINAL decoder layer's attention output, `o_proj`, and MLP, the
   final norm and the head are dead in production prefill: with the switch set they must stay unevaluated (marks for them take no
   arrays and add no time to a named phase). Test: a lazy sentinel on the chunk output / terminal-layer output is never evaluated
   with the switch set.
2. **Entry fence.** Before the first layer, evaluate this chunk's input embeddings and any position/mask setup under `other`
   (not a named phase), so layer 0 does not absorb embeddings, the vision tower or setup.
3. **Phase closure covers the state the phase writes.** `gdn` closes on the layer output AND the recurrent/conv state it stores in
   its cache entry. `attn_prep` includes an array mask when one is returned. `cache_post` closes on the cache state AFTER the
   eviction hook.
4. **Request-local handle.** The active handle is thread-local and owned by the profiler that published it; code running in
   another thread, or outside the profiled chunk in the same thread, sees `None`. Test with two threads.
5. **Layer hooks are valid only inside `Qwen3_5DecoderLayer`.** Attention marks are no-ops unless the enclosing decoder layer
   declared itself (models that reuse `Qwen3_5Attention` in another layer class report chunk-level phases only). Test with a tiny
   `qwen3_5_moe` model if one can be built without a checkpoint; otherwise a fake layer class reusing `Qwen3_5Attention`.
6. **Report.** Window lines every 32 chunks cover exactly those 32 chunks. The last line of a generation covers the REMAINING
   chunks since the previous window line (`final=1`; omitted if none remain). One extra line `[prefill_profile_total] …` gives
   generation-wide means, with the same fields. A profiler that disabled itself prints `broken=1` on its lines and never `final=1`
   for a partial record set. Finalisation runs from an outer `finally` and never masks the original exception.
7. **Tests really on CPU.** Fixtures bind the streams generation actually uses (including any stream object created at import
   time) to the CPU and assert CPU placement inside the model call. If that cannot be done, say so in the report.
8. Every changed line in an upstream-owned file carries or sits under a `# Fork (M57)` marker.

Known and accepted: the batched (non-session) prefill path has no hooks — a profiled run must confirm lines appear before trusting
an empty log; with the switch unset each layer hook costs one function call returning `None`.

## Amendment 2 (2026-10-04, after review round 2 of `aef10c6e` — both reviewers: correct for the planned qwen3_5 / MTP / native16 run; FIX-THEN-SHIP for the rest)

Binding.

1. Entry fence also evaluates precomputed `position_embeddings` when they exist. Its time is reported as its own field `entry=`
   (not `other`): the first chunk's value contains the whole-prompt embedding (and any vision work), as in production.
2. Every line carries `layers=<decoder layers that declared themselves in the window, per chunk>`. When it is 0 the cache state is
   evaluated right after the model call and reported as `forward=`; `cache_post` then never contains the forward pass.
3. The terminal layer is treated as dead only when the chunk kwargs carry no `capture_layer_ids` / `return_hidden`; "terminal" is
   the last layer actually executed, not a stored index.
4. An `observe` hook on a cache (EpiCache) is closed on the arrays it creates and reported as `observe=`; queries it consumes are
   live even in the terminal layer. Fix the module docstring accordingly.
5. A profiler that breaks before its first complete chunk prints one `[prefill_profile] chunks=0 broken=1 reason=<repr>` line.
6. Tests: execution-sensitive sentinels (wrap the terminal layer's `o_proj`, `linear_attn.out_proj`, `mlp`, the final norm and the
   head; assert none is evaluated with the switch set, with a positive control proving the sentinel fires when consumed); terminal
   KV update and terminal recurrent state ARE evaluated before their phase closes; the no-line test reads stderr once.

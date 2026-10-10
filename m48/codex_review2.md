**Do not bump this commit into the stack for A2–A6 yet.** P4 still has a state-corruption path, and P5 fails on the intended Qwen gate model with thinking enabled.

Reviewed HEAD `bb59774af75cf35ca30ce2d02baef1764141ffad`. Read-only verification used actual MLX classes on CPU: **46 retention tests passed, 1 skipped; 170 related snapshot/rewind tests passed.** No checkpoint weights or live gates were run.

**P1 — RESOLVED.** Full-sequence priming in [dispatch.py:1532]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1532), caller-metadata precedence in [ar.py:547]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:547), and cache-offset slicing in [language.py:1696]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1696) now compose correctly.

A tiny, randomly initialized Qwen3.5 hybrid model, using the actual VLM embedding method and language-model forward, produced:

| `prefill_step_size` | Positions received by successive forwards |
|---|---|
| `None` | `[160,161,162,163]` |
| `2` | `[160,161]`, `[162]`, `[163]` |
| `3` or `512` | `[160,161,162]`, `[163]` |

Every run finished at cache offset 164. The MoE language model inherits this implementation.

**P2 — RESOLVED by containment.** [snapshot.py:277]($HOME/ws/mlx-vlm/mlx_vlm/snapshot.py:277) refuses the layout mismatch before writing snapshot fields. Both [common.py:1216]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:1216) and the legacy **mid-prefill anchor path**, [dispatch.py:1462]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1462), clear the session.

I exercised both dispatcher branches using real rotating caches and the actual `_buffer_mtp_target_cache` conversion. Both ended with `cache=None`, `token_ids=None`, and the buffered-cache invariant intact. **Dropping the session is appropriate containment.** Affected rotating/MTP sessions can consequently require cold prefill every turn; retention for those configurations remains unachieved.

**P3 — RESOLVED for the reported reproduction.** [common.py:851]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:851) now checks the preceding window. With the actual window-4/buffer-32 cache:

```text
offset=37, start_position=33
rewind_safe(35)=False
rewind_safe(37)=True
```

Bypassing the guard still reproduces the original incomplete `[33,34,35]` history. Canonical prediction is disabled for rotating layers at [dispatch.py:1412]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1412).

**P4 — PARTIAL; still blocking.** The helper correctly raises at [common.py:1201]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:1201). However, dispatch handles the mismatch by selecting the legacy path at [dispatch.py:1397]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1397), which does not universally invalidate reuse.

Using the actual dispatcher and actual caches, with synthetic generation expanding 160 token IDs into 170 cache positions:

| Available anchor | Published IDs | KV offset | Recurrent state |
|---|---:|---:|---:|
| None | 160 | 160 | **after 171** |
| Valid anchor 100 | 100 | 100 | after 100 |
| Captured anchor 170 | 160 | **170** | **after 170** |

The no-anchor branch trims KV without restoring recurrent state at [dispatch.py:1488]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1488). The anchor branch also retains unchecked slicing at [dispatch.py:1478]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1478). **An unexplained offset mismatch should clear the session unless a valid token-to-position mapping is established.**

**P5 — OPEN; I reject the claimed Qwen scoping.** A **character-prefix** guarantee is insufficient; it must hold for token IDs.

Using the cached `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` tokenizer, the actual server template helper, `preserve_thinking=True`, and a content-only assistant echo:

```text
Generation tail: assistant\n<think>\n
History tail:    assistant\n<think>\n\n</think>\n\nHi.

Thinking ON:
prompt length=154; common token prefix=153
generation final token=198 ("\n")
history corresponding token=271 ("\n\n")
canonical suffix=None
selected rewind snapshot=44 (before user)
```

Thus the large user message is replayed. Thinking **off** passed this reproduction. The result also persisted with `fix_mistral_regex=True`.

The template creates these different newline sequences at [chat_template.jinja:124]($HOME/.cache/huggingface/hub/models--caslca--Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/snapshots/1dd70b36b8a800568576ad12fdeef3c7d3c2dc61/chat_template.jinja:124) and [chat_template.jinja:186]($HOME/.cache/huggingface/hub/models--caslca--Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/snapshots/1dd70b36b8a800568576ad12fdeef3c7d3c2dc61/chat_template.jinja:186). The prefix rejection at [openai.py:490]($HOME/ws/mlx-vlm/mlx_vlm/server/openai.py:490) is correct, but B1 cannot rescue retention afterward.

A shipped **character-level** counterexample is `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`, whose registry enables thinking: generation uses `<think>\n`, while content-only history uses `<think></think>`—[template:105]($HOME/.cache/huggingface/hub/models--mlx-community--NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit/snapshots/55ac8c89261109b36c04371cd3f479a4594208c8/chat_template.jinja:105), [template:186]($HOME/.cache/huggingface/hub/models--mlx-community--NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit/snapshots/55ac8c89261109b36c04371cd3f479a4594208c8/chat_template.jinja:186).

I accept limiting guarantees to verified **token-prefix-compatible** renderings. That limitation presently excludes the intended Qwen thinking-on/content-only case. The “kept regardless” claim in [serving-path.md:88]($STACK_REPO/docs/serving-path.md:88) remains inaccurate.

**P6 — PARTIAL.** The original continuation reproduction now passes using actual retirement calls, ring size 3:

```text
retire 200 → [100 pinned, 200, 201]
retire 240 → [100 pinned, 240, 241]
retire 280 → [100 pinned, 280, 281]
edit at 120 → rewind 100
```

An edit rewind and subsequent retirement also preserved the pin. However, the new pin implementation introduces P9 below.

**P7 — RESOLVED.** The hook travels through request-local kwargs, [QueuedGenerationRequest:1000]($HOME/ws/mlx-vlm/mlx_vlm/server/generation.py:1000), queue construction at [generation.py:1536]($HOME/ws/mlx-vlm/mlx_vlm/server/generation.py:1536), worker dispatch at [generation.py:2481]($HOME/ws/mlx-vlm/mlx_vlm/server/generation.py:2481), and generation kwargs at [generation.py:1669]($HOME/ws/mlx-vlm/mlx_vlm/server/generation.py:1669). Dispatch pops it before model execution. The forwarding test passes; another request no longer replaces this hook on the shared session.

**P8 — PARTIAL.** The added tests cover useful portions of the original findings:

- **P1:** full-position metadata reaches a fake LM; actual LM slicing remains untested in the committed suite.
- **P2/P3:** actual rotating-class mismatch and unsafe-window reproductions.
- **P4:** helper rejection, **not the unsafe dispatcher fallback**.
- **P5:** character-tokenized fixtures; they miss the shipped tokenizer’s newline merge.
- **P6:** eviction with a fixed pin; the continuation test directly appends snapshots rather than retiring requests.
- **P7:** worker forwarding.
- **Speculation:** the new test enters a mocked speculative handoff with a non-null drafter. It proves capture ordering, but does not execute actual MTP rounds.

See [test_prompt_end_retention.py:429]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prompt_end_retention.py:429) onward. Recorded client-echo fixtures and live parity remain outstanding.

**P9 — NEW: an existing snapshot cannot acquire the latest-user pin.** [snapshot.py:124]($HOME/ws/mlx-vlm/mlx_vlm/snapshot.py:124) returns on an equal offset **before** applying `pinned=True`.

After successful B2 retirement at 161, let the next user start at 161 and retire at 201:

```text
before: [100 pinned, 160, 161]
after:  [100 pinned, 200, 201]
edit new user at 180 → rewind 100, expected 161
```

The valid latest-user anchor is evicted while an obsolete anchor remains pinned. Promote an existing entry when it becomes the latest-user anchor, and test this through retirement.

| Finding | Verdict |
|---|---|
| P1 — absolute RoPE positions | **RESOLVED** |
| P2 — rotating layout restoration | **RESOLVED** through session drop |
| P3 — buffered rewind window | **RESOLVED** |
| P4 — offset mismatch containment | **PARTIAL** |
| P5 — retention/template guarantee | **OPEN** |
| P6 — anchor preservation | **PARTIAL** |
| P7 — request-scoped hook | **RESOLVED** |
| P8 — regression coverage | **PARTIAL** |
| P9 — existing-anchor pin promotion | **OPEN — NEW** |

**Overall verdict: not fit for the stack bump yet.** Fix P4, retain a stable token boundary for P5, and repair P9 with dispatcher-level and real-tokenizer regressions. Then run A2–A6; the passing CPU suites do not establish those live acceptance criteria.
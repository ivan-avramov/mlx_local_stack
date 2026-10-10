1. **P1 — BLOCKING: canonical prefill loses absolute RoPE positions.**  
   [dispatch.py:1486]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1486) passes only cache-shaping kwargs. Qwen3-VL and the Qwen3.5 VLM wrapper compute positions from the **canonical suffix alone** ([qwen3_vl.py:58]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_vl/qwen3_vl.py:58), [qwen3_5.py:73]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/qwen3_5.py:73)). Their language models then interpret those positions against the existing cache offset.

   Reproducing the actual position-slicing code with `prompt_end=160`, canonical length 4:
   - Chunked forward of 3 tokens receives **empty positions**, from slicing `[160:163]` out of four positions.
   - Unchunked forward receives positions **0–3**, instead of **160–163**.

   The first case can throw and silently reduce B2 to B1; the second can persist incorrect KV despite perfectly matching token IDs. The existing cached-prefix path explicitly prevents this problem at [dispatch.py:782]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:782). Canonical prefill needs equivalent position handling. The `qwen3_5_text` embedding wrapper does not have this particular suffix-position behavior.

2. **P2 — BLOCKING: MTP can change the rotating-cache layout between capture and restoration.**  
   Capture happens at [ar.py:721]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:721). Afterwards, MTP invokes `_buffer_mtp_target_cache`, replacing ordinary rotating layers with `BufferedRotatingKVCache` ([utils.py:389]($HOME/ws/mlx-vlm/mlx_vlm/speculative/utils.py:389), [mtp.py:579]($HOME/ws/mlx-vlm/mlx_vlm/speculative/mtp.py:579)). Retirement restores the earlier snapshot into that replacement without converting its layout ([snapshot.py:260]($HOME/ws/mlx-vlm/mlx_vlm/snapshot.py:260)).

   A reproduction using the actual cache methods with NumPy arrays produced:

   ```
   After MTP conversion: offset=10, start_position=6, _idx=4
   After snapshot restore: offset=10, start_position=0, _idx=2
   ```

   The buffered cache requires `offset == start_position + _idx`; restoration breaks it. This affects B1 restoration itself, even without canonical prefill. Capture after establishing the final cache representation, or restore through a representation-aware conversion.

3. **P3 — BLOCKING: buffered SWA rewinds can silently lose required attention history.**  
   The guard at [common.py:857]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:857) checks whether the *rewind position* remains available, rather than whether its required preceding window remains available. Buffered rotating caches report themselves trimmable ([cache.py:2284]($HOME/ws/mlx-vlm/mlx_vlm/models/cache.py:2284)), so the subsequent non-trimmable-cache guard does not rescue them.

   Actual-method reproduction: window 4, buffer 32, append tokens 0–36, then rewind from 37 to 35. Both dispatch guards permit reuse. After replaying token 35, available KV is `[33,34,35]`; the required window is `[32,33,34,35]`.

   B2 makes assistant-echo mismatch a normal trigger for this existing weakness. Ordinary wrapped `RotatingKVCache` instead reaches the non-trimmable guard and, without a DeltaNet snapshot, falls back to full prefill. Persist rotating rewind snapshots or validate the entire required window before reuse.

4. **P4 — BLOCKING: offset mismatch logs a warning but publishes an inconsistent session.**  
   [common.py:1201]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:1201) cannot repair expanded multimodal offsets with `ids[:prompt_end]`.

   CPU reproduction with 160 prompt IDs and captured offset 170 left:

   ```
   len(token_ids)=160
   KV offset=170
   recurrent state=state-after-170
   ring offsets=[100,170]
   ```

   On the next matching request, dispatch sees a complete 160-token match, bypasses recurrent rewind, and trims KV to 160 while leaving recurrent state at 170. That is silent state corruption. Disabling canonical rendering for media does **not** disable this retirement branch. An unexplained mismatch must invalidate reuse, or use an explicit token-to-cache-position mapping.

5. **P5 — SHOULD-FIX: B1 fallback does not universally preserve the large user turn.**  
   The canonical prefix check correctly rejects incompatible renderings ([openai.py:490]($HOME/ws/mlx-vlm/mlx_vlm/server/openai.py:490)), but retaining the complete generation prompt is insufficient when the generation-only assistant header changes in history.

   Concrete template repro: generation ends with `assistant\n<think>\n`; historical assistant rendering starts with `assistant\n{content}` and ignores `preserve_thinking`. The next request diverges **before prompt_end**. A DeltaNet session therefore selects the before-user snapshot at [dispatch.py:1017]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1017), replaying the entire large user/tool-result message. Pure attention can retain more, but still reports fewer cached tokens than the complete opener.

   Either retain a stable boundary after the user message but before the unstable generation header, or explicitly limit the retention guarantee to compatible templates.

6. **P6 — SHOULD-FIX: repeated continuations can evict the still-relevant before-user anchor.**  
   When the latest recognized user marker remains behind the reused cache, [ar.py:605]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:605) captures the current cache offset as the “anchor.” Retirement then appends newer snapshots into the ordinary FIFO ring ([common.py:1228]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:1228), [snapshot.py:132]($HOME/ws/mlx-vlm/mlx_vlm/snapshot.py:132)).

   CPU reproduction with the same latest user beginning at 100 and successive prompt ends 160, 200, 240 leaves `[160,200,240]`. Editing that user at token 120 finds **no snapshot**, forcing full prefill. This applies to continuation/template shapes that do not introduce another recognized user marker. Preserve the actual latest-user anchor separately or give it eviction priority.

7. **P7 — SHOULD-FIX: the canonical hook is mutable session state, not request state.**  
   [openai.py:2239]($HOME/ws/mlx-vlm/mlx_vlm/server/openai.py:2239) overwrites `canonical_suffix_fn` before queueing generation; dispatch reads it only after generation at [dispatch.py:1394]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1394).

   Repro: request A generates while request B resolves the same chat ID and installs its closure. A then retires using B’s messages/tools/template settings. GPU-request serialization does not serialize these HTTP-thread assignments. Usually the prefix check rejects the prediction, losing B2; media B can simply replace the hook with `None`.

   I found no subsequent mutation of the captured message/template containers within the same endpoint invocation. The concrete race is replacement of the shared hook. Carry it in the queued request. The newly added tokenizer borrow retries address a separate concurrency failure.

8. **P8 — SHOULD-FIX: tests do not exercise the principal B2 and MTP contracts.**  
   The `draft=True` test still sets `draft_model=None` ([test_prompt_end_retention.py:98]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prompt_end_retention.py:98)); both parameterizations exercise ordinary decoding. Retirement tests replace canonical prefill with an offset increment ([test_prompt_end_retention.py:137]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prompt_end_retention.py:137)). The canonical fixture uses character tokenization and a generation header without a thinking opener ([test_prompt_end_retention.py:285]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prompt_end_retention.py:285)). These tests cannot detect P1–P5.

   Client echo also needs recorded request fixtures. The checked-in opencode configuration uses `@ai-sdk/openai-compatible`, not the OpenAI SDK. The current AI SDK converter sends nonempty reasoning as `reasoning_content`; opencode also supports an explicit interleaved-reasoning mapping. Neither establishes the behavior of the installed version. [AI SDK converter](https://raw.githubusercontent.com/vercel/ai/main/packages/openai-compatible/src/chat/convert-to-openai-compatible-chat-messages.ts), [opencode transform](https://raw.githubusercontent.com/anomalyco/opencode/dev/packages/opencode/src/provider/transform.ts).

   OpenWebUI’s structured-reasoning replay depends on provider configuration: default connections omit it, `llama.cpp` sends `reasoning_content`, and Ollama reconstructs tagged content. Inline tagged reasoning can also round-trip. Thus `<think>\n\n</think>\n\n{content}` predicts only the content-only case. On mismatch after prompt_end, a healthy DeltaNet ring preserves the user turn but pays the wasted canonical prefill **plus** replay of the actual assistant history. SWA additionally encounters P3. [OpenWebUI replay documentation](https://docs.openwebui.com/features/chat-conversations/chat-features/reasoning-models/).

The tree changed during review. The latest inspected version includes both DeltaNet list-copy fixes; CPU-only reproductions confirmed that failed canonical prefill now restores the original recurrent state and subsequent writes do not mutate the ring entry. I made no changes. Pytest could not start because importing MLX failed with “No Metal device available”; reproductions above executed extracted source methods with scalar/NumPy substitutes.

| Criterion | Verdict | Evidence and limits |
|---|---|---|
| **A1 — unit contract** | **FAIL** | Nominal fake retirement arithmetic and canonical fixture assertions are present, but the rewind guarantee fails under P6 and SWA under P2/P3. `drop_after(divergence)` followed by assigning prompt IDs before `update()` is sound **when offsets and snapshots actually describe those IDs**; P4 violates that prerequisite. Without a recognized user marker, prompt-end capture still works, but an earlier edit may require full prefill. |
| **A2 — DeltaNet live reuse** | **CANNOT-JUDGE** | For an unchanged, compatible text prompt, expected turn-2 reuse is prompt_end, or prompt_end plus matching canonical tokens—not necessarily exact equality. P5, eviction, unavailable/disabled rewind snapshots, and rejected media/RoPE reuse can defeat the opener-length target. No live 8K/32K/64K or eviction measurements performed. |
| **A3 — pure-attention control** | **CANNOT-JUDGE** | Ordinary full-attention KV follows the same intended retention policy without DeltaNet snapshots. P1 affects applicable RoPE models; P2/P3 affect rotating architectures; P5 can reduce the matched prefix. Architecture-neutral acceptance is unproven. |
| **A4 — opencode/tool results** | **CANNOT-JUDGE** | A matching large tool-result prefix is retained by B1. Detected assistant tool calls return `None` at [openai.py:470]($HOME/ws/mlx-vlm/mlx_vlm/server/openai.py:470), so the following request prefills the echoed assistant/tool-call turn plus new input. That meets the handoff’s relaxed B1 target, not “new user only.” P5 remains a counterexample; the 20K tool-result run is outstanding. |
| **A5 — output parity** | **FAIL** | P1–P4 provide incorrect-state paths for later cached generation. For fresh requests, capture is correctly after the final `_step` and before speculative handoff; capture arguments do not leak into model kwargs, and MTP hidden/shared-KV capture remains intact ([ar.py:487]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:487)). The added `mx.eval` is a synchronization/materialization change, not an added sampling operation; nevertheless bitwise parity needs measurement. Canonical prefill is greedy and performs no decode step at `max_tokens=0`. Quantization/preallocation settings are mostly preserved, but position metadata and `serialize_kv_quantization` are omitted. |
| **A6 — memory** | **CANNOT-JUDGE** | Successful B2 normally leaves three ring entries with ring size 3; the canonical-end entry shares arrays with live state. Captures copy Python lists, retaining older array buffers rather than eagerly copying every DeltaNet tensor. “Before: one” is an opener observation, not a universal steady-state baseline: the old ring could also accumulate three entries. No unbounded cross-request capture-list leak found. Canonical prefill uses the same cache, but ordinary KV growth/conversion, pinned generation outputs, and rotating snapshots can cause transient duplication. The obsolete first-yield rotating capture still runs at [dispatch.py:1268]($HOME/ws/mlx-vlm/mlx_vlm/generate/dispatch.py:1268), alongside before-user and prompt-end captures. Full-stack pressure/swap acceptance remains unmeasured. |

**Overall verdict: do not land B1+B2 as accepted in this form.** The capture location and corrected DeltaNet snapshot ownership are sound, but absolute-position handling, MTP rotating-layout restoration, buffered-window rewind safety, and offset mismatch containment have concrete correctness failures. Fix those, add real canonical-prefill and speculative-path tests, then run the registered live parity, client-echo, reuse, and full-stack memory gates.
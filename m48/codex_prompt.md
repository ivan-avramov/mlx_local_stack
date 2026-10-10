You are a cold, adversarial design+code reviewer. Read-only. Repos under this directory:
`mlx-vlm/` (fork of Blaizzy/mlx-vlm; the change under review is UNCOMMITTED: run `git -C mlx-vlm diff HEAD`
and `git -C mlx-vlm status`) and `mlx_local_stack/` (the stack; spec at
`mlx_local_stack/docs/specs/c102b-prompt-end-retention.md`, background in `mlx_local_stack/docs/handoff.md`
section "NEXT: M48").

THE CHANGE (M48 / C102(b), B1+B2 together): on asymmetric-rendering (thinking-template) sessions the worker
used to retire the per-chat cache at a snapshot BEFORE the latest user message, so every request re-prefilled
its own last user turn. Now `generate_step` captures the cache state at PROMPT END (after the final prompt
`_step`, before speculative/decode), the retire path (`generate/common.py::_retire_asymmetric_session`,
called from `generate/dispatch.py`) restores that state, trims KV to prompt_end, keeps the before-user anchor
in the DeltaNet snapshot ring, then prefills the CANONICAL history rendering of the assistant turn predicted
by the server (`server/openai.py::_canonical_assistant_suffix`, hook `PromptCacheState.canonical_suffix_fn`)
via a prompt-only `generate_step(max_tokens=0)` (`dispatch.py::_prefill_canonical_suffix`), and stores
`token_ids[:prompt_end + canonical_len]`. Toggle `--cache-session-retain-prompt-end` (default on) /
`MLX_VLM_SESSION_RETAIN_PROMPT_END`. Tests: `mlx_vlm/tests/test_prompt_end_retention.py`. Snapshot ring:
`mlx_vlm/snapshot.py::capture_states`. Related existing code to read: `generate/ar.py` (prefill loop, the
`_step` hook, `run_speculative_rounds` hand-off), `generate/dispatch.py` (prefix reuse + rewind guard ~L990-1080,
post-generation branch ~L1370-1460), `generate/common.py` (`PromptCacheState`, `_capture_anchor_state`,
`_trim_cache`), `server/openai.py` (session resolve + template render ~L2080-2180), `server/session_manager.py`,
`server/cli.py`.

Review AGAINST these pre-registered criteria (from the spec) and report per criterion PASS / FAIL / CANNOT-JUDGE
with evidence (file:line):
A1 Unit (fake caches): retire offset == prompt_end + canonical_len; canonical assistant tokens equal the
   template's history rendering for the same content; a diverging last user turn still rewinds to the
   before-user anchor; a diverging assistant echo rewinds to prompt_end.
A2/A3 (live, not runnable here): would the code make turn-2 `cached_tokens` equal the opener length on a
   DeltaNet hybrid (Qwen3.5-family) AND on a pure-attention model? Identify any path where it would not.
A4 opencode: tool results are user-role messages and most assistant turns carry tool_calls. Does the design
   retain a large tool result across the next request? What is the behaviour on tool-call turns?
A5 Output parity: could this change the generated TEXT of a fresh (uncached) request, or of a cached request
   whose prefix matched? Consider MTP ON (speculative_prefill capture kwargs, `run_speculative_rounds`) and OFF,
   the `mx.eval` inserted before the capture, the canonical prefill's kwargs subset, RoPE/position state after
   a prompt-only generate_step on a live cache (Qwen3-VL-style rope deltas), and quantized-KV/prealloc caches.
A6 Memory: snapshots per session at rest (before: 1; claim: 3 with canonical), refcount vs copies, any leak
   of the mid-prefill capture lists across requests, any double-buffer during the canonical prefill.
Also check: (i) ring monotonic rule + `drop_after` interplay with `PromptCacheState.update`'s own divergence
drop (`_retire_asymmetric_session` sets `token_ids` before update — is that sound?); (ii) the fallback when the
prompt has no recognised user marker (`snapshot_at_offset is None`) — the retire path now runs with an empty
anchor capture; (iii) failure containment: canonical rendering exceptions, canonical prefill exceptions,
`prompt_end != len(prompt ids)` (multimodal token expansion); (iv) the server hook closes over
`processed_messages`/`template_kwargs`/`tools` — any mutation after the closure is built? thread-safety with
the GPU thread; (v) `preserve_thinking=True` cache-alignment kwarg: the canonical form renders
`<think>\n\n</think>\n\n{content}`; what does an OpenAI-SDK client (opencode) and OpenWebUI actually echo,
and what happens on mismatch (cost, correctness)? (vi) anything that could corrupt a session silently
(wrong offset, stale DeltaNet state, rotating (SWA) layers on Gemma-style models).

Output: a numbered list of findings, each tagged BLOCKING / SHOULD-FIX / NIT, with file:line and a concrete
repro or reasoning, then the per-criterion verdict table, then a one-paragraph overall verdict.

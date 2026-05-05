Here is the fully updated, production-ready context memory, incorporating our latest architectural discoveries regarding step-padding and the SWA memory hole.

***

**System Overview: Local Gemma-4 Vision-MoE + OpenWebUI Pipeline**

**Goal:** We successfully built a flagship-tier local AI pipeline using quantized Gemma 4 (31B 6-bit) running on Apple Silicon via `mlx-vlm`, interfaced with OpenWebUI.

**Capabilities Achieved:** Native multimodal vision, agentic web searching, autonomous multi-tool execution (e.g., sequentially writing and executing Python scripts in Pyodide to self-verify math), document RAG, multi-turn accordion thought blocks (`<think>`), perfect LaTeX math rendering, and a highly-optimized 128k/256k context window (for the gemma-4-31B-6bit/gemma-4-31B-4bit models respectively)

**Current Workload:** Autonomous Agentic Coding. We specifically run the 6-bit quantization to prioritize lossless reasoning, strict JSON adherence, and rigid syntactic logic over the 4-bit model's larger context window.

**Why mlx-vlm instead of mlx-lm?**
While `mlx-lm` works fine out of the box for text-only Gemma 4, we explicitly built on top of `mlx-vlm` because we must have the ability to process visual tensors (screenshots, image uploads, and document PDFs) alongside the text and tool-calling agentic loops.

**The Core Architecture Fixes (Minimalist Production Build)**

**1. Tokenizer Race Condition (utils.py)**
* **The Problem:** Words leaked out of the thought block after the closing `<channel|>` tag due to a race condition in the custom `_ChannelTokenDetokenizer`.
* **The Fix:** Deleted the custom wrapper class. We now rely entirely on the native tokenizer and `StoppingCriteria`, which perfectly streams tokens in chronological order.

**2. The StreamingTranslator Engine & Token Un-Fuser (server.py)**
* **The Problem:** OpenWebUI requires `<think>` instead of Gemma's native `<|channel>thought`. Furthermore, quantization degraded the model's attention mechanism on the very first token of a zero-shot prompt, causing token space-fusion (e.g., generating "Thisis").
* **The Fix:** Built a robust, stateful `StreamingTranslator` with a 15-character delay buffer to translate tags mid-stream without tearing. Added a surgical regex bound to an `is_beginning` flag to dynamically un-fuse missing spaces on targeted vocabulary words.

**3. Vision Schema Alignment (server.py)**
* **The Problem:** OpenWebUI sends images as `{"type": "image_url"}`, but the Hugging Face `gemma_4_template.jinja` requires `{"type": "image"}` to render the `<image>` visual token. The model was going blind.
* **The Fix:** Updated the `message.content` parser to intercept `image_url` and rewrite it to `type: image`, perfectly aligning the prompt with the visual tensors.

**4. Tool Parsing & OpenAI API Strictness (server.py)**
* **The Problem:** OpenWebUI's Pydantic validation crashes if tools don't perfectly match the OpenAI spec.
* **The Fix:** Implemented a lightweight `_resolve_tool_calls` wrapper. It lets the native MLX `process_tool_calls` do the heavy parsing, but safely injects the mandatory `id`, `type="function"`, and `json.dumps()` stringified arguments that OpenWebUI demands.

**5. Processor Chat Template Fallback (prompt_utils.py)**
* **The Problem:** AutoProcessor models frequently fail to expose their `chat_template`, causing mlx-vlm to fall back to a raw, broken prompt.
* **The Fix:** Added a fallback block inside `apply_chat_template` that checks if `processor.chat_template` is missing, and natively inherits it from `processor.tokenizer.chat_template`.

**7. The Quantization Interceptor Bug (generate.py)**
* **The Problem:** The pipeline was blowing past 64GB of RAM on long contexts because `maybe_quantize_kv_cache` was only checking for `cache.KVCache`, failing to intercept and quantize Gemma's newer `cache.SimpleKVCache` and `cache.ChunkedKVCache`.
* **The Fix:** Added the newer cache types to the `isinstance` tuple, allowing the pipeline to successfully migrate FP16 histories into 4-bit `TurboQuantKVCache` at the `QUANTIZED_KV_START` (5000) threshold.

**8. The Threshold Graph Explosion (generate.py)**
* **The Problem:** When breaching the 5000-token threshold, MLX lazily built FP32 intermediate buffers for all 64 layers simultaneously, causing a massive 9GB+ out-of-memory spike during compilation.
* **The Fix:** Serialized the graph compilation by injecting `mx.eval(prompt_cache[index].keys, prompt_cache[index].values)` directly inside the layer loop. This compiles and frees the intermediate FP32 buffers layer-by-layer, dropping the threshold spike to ~150MB.

**9. The Double-Buffer Reallocation Spike (server.py & turboquant.py)**
* **The Problem:** Late-stage cache geometric growth (e.g., 76K -> 95K tokens) required the GPU to hold both the old and new cache in VRAM simultaneously, creating a massive 11GB+ double-buffer memory spike.
* **The Fix:** Removed the `MAX_KV_SIZE` override in `server.py` and threaded the environment variable all the way down into the `TurboQuantKVCache` constructor. By hardcoding `MAX_KV_SIZE=131072` upfront, the backend statically pre-allocates the entire 130K block, entirely bypassing O(N^2) reallocation thrashing and late-stage OOM crashes.

**10. The Prefill "Goldilocks" Zone (server.py)**
* **The Problem:** `PREFILL_STEP_SIZE=2048` created a massive 9.3GB $N^2$ activation memory spike during prompt ingestion. `128` crashed the Metal driver due to unrolled shader alignment assumptions.
* **The Fix:** Hardcoded `PREFILL_STEP_SIZE=512`. On Apple Silicon's UMA, this shrinks the activation footprint by nearly 5GB without sacrificing any `prompt_tps` throughput, avoiding macOS GPU watchdog kills.

**11. Telemetry Pipeline (server.py)**
* **The Problem:** Server usage metrics (tokens, TPS, peak memory) were vanishing into the API ether.
* **The Fix:** Injected `logging.info` blocks across all four OpenAI-compatible endpoints (`/chat/completions` and `/responses`, both streaming and non-streaming) to pipe live generation metrics directly into `log_file`.

**12. The Multi-Cache LRU Manager (server.py)**
* **The Problem:** OpenWebUI background tasks (e.g., chat titles, tags) used distinct prompt structures, triggering cache divergence. Since the server originally used a single-slot cache, these background tasks constantly destroyed the 45GB main chat context.
* **The Fix:** Implemented a `MultiCacheManager` using `OrderedDict`. It tracks multiple sessions independently and dynamically evicts dormant Least Recently Used (LRU) caches when macOS active unified memory breaches a configurable limit (e.g., 10% free RAM).

**13. Mid-Prefill Allocation Hooks (turboquant.py & server.py)**
* **The Problem:** Caches could scale geometrically mid-prefill. Request-boundary eviction was unsafe, as massive context growth could hit the VRAM ceiling and OOM crash before the manager regained control.
* **The Fix:** Injected `_trigger_allocation_hooks()` directly into `turboquant._reserve_state_capacity`. The Metal allocator now calls back to the Python memory manager to halt the thread and purge dormant LRU sessions on demand to satisfy contiguous memory requests.

**14. RoPE Desync, Step-Padding, and the SWA Memory Hole (generate.py)**
* **The Problem:** Rewinding context during a chat branch caused severe hallucination loops. Padded standard caches (inflated by `PREFILL_STEP_SIZE`) bypassed shape-based slice checks, leaving ghost tokens. Worse, Gemma 4 uses Sliding Window Attention (`RotatingKVCache`). Rewinding and zeroing out a ring buffer created a "Memory Hole" (since past tokens are permanently overwritten), causing massive uniform probability anomalies during Softmax ($e^0 = 1.0$).
* **The Fix:** Implemented a type-aware "Smart Rewind". For SWA ring buffers, an interception guard automatically invalidates the prefix cache and forces a full, clean re-prefill to rebuild mathematical integrity. For standard dynamic caches, the arrays are unconditionally physically sliced to strip both ghost tokens and step-padding, ensuring RoPE indices remain perfectly aligned.

**15. Single-Worker Queue Bottlenecks (OpenWebUI)**
* **The Problem:** Follow-up questions appeared to hang the server. In reality, OpenWebUI was firing sequential background tasks to the 31B model, monopolizing Uvicorn's single worker queue while the UI waited.
* **The Fix:** Identified as an architectural constraint. Required configuring OpenWebUI to isolate "Task Models" (titles, tags, autocomplete) to a secondary, lightweight local API (e.g., 2B quantization) to keep the primary reasoning worker unblocked.

**16. The Tool Call Swallower (server.py)**
* **The Problem:** If the model stuttered and hallucinated a broken `<|tool_call>` sequence, the `StreamingTranslator` buffered the output indefinitely waiting for valid JSON, effectively silencing the stream and hanging the UI.
* **The Fix:** Patched the stream generator to safely rescue and yield the buffered text as standard conversational output if a tool call fails to resolve, preventing silent drops.

**17. The Ghost Prompt Math Guard (server.py)**
* **The Problem:** Removing the system prompt untethered the models from strict LaTeX structural rules. They drifted into incompatible Markdown dialects (e.g., failing to isolate `$$` blocks with blank lines, or missing delimiters entirely), breaking OpenWebUI's Markdown-It/KaTeX parser and causing severe UI rendering artifacts.
* **The Fix:** Dynamically injected a hidden "Ghost Prompt" (`"Enclose inline math in \( and \). Enclose display math in \[ and \] on their own lines."`) directly into `processed_messages` inside the `chat_completions_endpoint`. This forces rigid KaTeX compliance at the API layer without polluting the user-facing UI.

**19. The Pyodide Tool-Call "Phantom Stall" (server.py + OpenWebUI)**
* **The Problem:** A simple "build a SuperMario level" prompt to Qwen3.6-27B-UD-MLX-6bit appeared to wedge the backend for 23+ minutes — the UI froze on a brief intro line and emitted nothing further. The mlx_vlm log showed only one `Prefix Cache Telemetry` line; `lsof` confirmed an ESTABLISHED socket; `nettop` showed `bytes_out` frozen for many seconds at a time; `sample <pid>` showed the GPU thread mostly parked in `_pthread_cond_wait` inside `mlx::core::eval_impl` with sporadic `qmv` / `concatenate_gpu` dispatches. Initial hypothesis: scheduler hang in continuous batching, allegedly "unblocked" by sending a parallel request.
* **The Diagnosis:** False alarm. The model was emitting an ~11k-token `<tool_call>{...}</tool_call>` body containing a Python `execute_code` call to OWUI's Pyodide tool — the entire HTML game source as a string argument. **OWUI's frontend deliberately hides streaming tool-call markup until the call closes**, so the user saw silence even though tokens flowed continuously at ~6-8 tok/s. Server log timestamps confirmed: request started 19:56:21, follow-up summary request landed at 20:19:30 with `Prompt Delta: 11227` (= the prior tool-call body fed back as context). The "parallel-test unblock" was coincidence — could not reproduce under controlled tests; the summary request just happened to finish near the same moment. Also confirmed there is no batching scheduler bug in `_run` / `BatchGenerator._step` — the loop polls `requests.get_nowait()` while `active` is non-empty and the double-buffered `mx.async_eval` + `mx.eval` decode pattern is sound.
* **The Side-Note:** `main_models.yaml`'s Qwen3.6 entry has no `tool_call_parser` and only `gemma4.py` exists in `mlx_vlm/tool_parsers/`, so `suppress_tool_call_content` is a no-op for Qwen3 — raw `<tool_call>` markup streams as `delta.content` and OWUI's frontend handles it. Adding a `qwen3` parser would let the server emit structured `tool_calls` chunks but isn't required for OWUI integration.
* **The Mitigation (not a fix):** When this pattern appears, check the server log for a follow-up request with non-trivial `Prompt Delta` — it proves the prior request finished and reveals the actual output token count. Real waits for big tool-call bodies on this 27B/6-bit model are 5-25 min.

**18. Test results**
- {'model': 'mlx-community/gemma-4-31b-it-4bit', 'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'The provided text consists of the phrase "the quick brown fox jumps over the lazy dog" repeated hundreds of times, which is a famous English pangram used to display all the letters of the alphabet.', 'tool_calls': None, 'tool_call_id': None, 'name': None}}], 'usage': {'input_tokens': 262196, 'output_tokens': 41, 'total_tokens': 262237, 'prompt_tps': 124.49054785929356, 'generation_tps': 6.022604413156167, 'peak_memory': 44.605387124}}
- {'model': 'mlx-community/gemma-4-31b-it-4bit', 'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'The provided text consists of the repeated phrase "the quick brown fox jumps over the lazy dog," which is a famous English-language pangram containing every letter of the alphabet.', 'tool_calls': None, 'tool_call_id': None, 'name': None}}], 'usage': {'input_tokens': 242196, 'output_tokens': 36, 'total_tokens': 242232, 'prompt_tps': 144.69207367312902, 'generation_tps': 7.291513415100981, 'peak_memory': 36.795019636}}
- {'model': 'mlx-community/gemma-4-31b-it-4bit', 'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'The provided text consists of the phrase "the quick brown fox jumps over the lazy dog" repeated numerous times, which is a famous English pangram containing every letter of the alphabet.', 'tool_calls': None, 'tool_call_id': None, 'name': None}}], 'usage': {'input_tokens': 130053, 'output_tokens': 37, 'total_tokens': 130090, 'prompt_tps': 231.18348909643635, 'generation_tps': 10.861279398143393, 'peak_memory': 29.019992436}}
-  {'model': 'mlx-community/gemma-4-31b-it-4bit', 'choices': [{'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': 'The provided text consists of the phrase "the quick brown fox jumps over the lazy dog" repeated hundreds of times, which is a famous English pangram containing every letter of the alphabet.', 'tool_calls': None, 'tool_call_id': None, 'name': None}}], 'usage': {'input_tokens': 81124, 'output_tokens': 38, 'total_tokens': 81162, 'prompt_tps': 330.77773670813724, 'generation_tps': 15.106347443705085, 'peak_memory': 25.684406646}}

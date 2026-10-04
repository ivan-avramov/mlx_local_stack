# Proposal: swappable image generation for OpenWebUI

Recorded: 2026-10-03. Status: deferred proposal; implementation and live qualification are not authorized by this document. `docs/PLAN.md` remains the only execution queue.

## Outcome and scope

Add `Qwen/Qwen-Image-2.1` as an optional image-generation target for OpenWebUI, sharing the heavyweight-worker lifecycle with the chat models. Start with swapping, not permanent co-residency. Preserve the separately hosted task and embedding service.

Deliver text-to-image first, then reference editing and transparent output. Qualify 1024-pixel generation before 2048-pixel output. No model weights are bundled with the stack; operators obtain their own instances. Jive, Jev and decision-model composition are outside this proposal.

## Evidence and uncertainties

The advertised 7B parameters describe the diffusion transformer, not the complete pipeline. The pipeline also needs a roughly 8B text/vision encoder and a VAE. Approximate weight-file sizes assessed during this session:

| Component | Original BF16 files | `mlx-community/Qwen-Image-2.1-MLX-4bit` files |
|---|---:|---:|
| Diffusion transformer | 14.2 GB | 4.00 GB |
| Text/vision encoder | 17.5 GB | 5.13 GB |
| VAE | 1.4 GB | 1.35 GB |
| Total | 33.1 GB | 10.5 GB |

These are storage figures, not generation peaks. Quantized checkpoint compatibility and quality are unverified in this stack. The image pipeline uses conditioning-prefix KV caching and substantial attention/activation/decode buffers; it does not accumulate a conversational cache in the same way as a chat model.

MFLUX supplies native MLX inference. Its original text-generation path leaves the encoder in BF16 despite transformer quantization. Its newer reference/editing path can quantize eligible transformer and text/vision encoder layers, supports RGBA output and tiled VAE decoding, and is the preferred candidate for qualification. These paths have different precision and output contracts; select and pin one explicitly. Do not assume a community quantized export loads correctly in either path.

Upstream validation includes successful generation, edits, transparency and quantized reloads, alongside unsuccessful instruction-following examples. It is not a quality certification for our workloads or hardware. Treat runtime, model and quantization revisions as one recipe.

The recorded near-256K prefill peak of `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` is about 47.16 GB (see `stack-certification-2026-09-14.md`). It does not establish idle residency or combined image/chat capacity. Co-residency is deferred until combined measurements support it. CPU offloading on a unified-memory Mac does not create additional physical memory.

## Proposed architecture

```text
OpenWebUI
  chat requests  -> mlx-serve router -> selected chat worker
  image requests -> mlx-serve router -> native MLX image worker
  task/embedding requests           -> existing auxiliary service
```

The router owns one exclusive heavyweight inference slot, covering both chat and image endpoints and the complete request lifetime, including streaming and cancellation. Separate chat/image locks are insufficient.

Switching sequence:

1. Finish the active heavyweight request; queue the next request.
2. Unload the current worker and verify process termination and resource release.
3. Start the requested worker in its isolated dependency environment; wait for readiness.
4. Serve the request while retaining exclusive ownership of the slot.
5. On a later request for another target, repeat the switch.

Keep the worker loaded for subsequent requests to the same target under a bounded idle policy. Cancellation and failures must not release the router slot while GPU work survives. Do not retry a failed request automatically and duplicate generation. If a switch fails, return an explicit error; subsequent recovery must be observable.

OWUI retains chat messages after a switch, but the unloaded chat worker loses its KV cache. Returning to chat therefore incurs model load and conversation prefill. Measure that cost at ordinary and long context before calling the integration practical. Do not promise transparent preservation of execution state, only conversation content.

## Runtime qualification

Pin the checkpoint, source commit, dependencies, component precisions, sampler, steps, guidance, resolution, seed, reference budget and any tiling. Use a native macOS worker; OWUI can remain in Docker. Keep downloads/caches and output artifacts within the project-approved locations.

1. Establish a higher-precision standalone reference and a small seeded pilot with batch size one.
2. Compare quantized transformer and encoder recipes against that reference. Review composition, typography, identity and instruction adherence; define the quality rubric and acceptance threshold before running comparisons.
3. Qualify 1024-pixel generation; record cold-load peak separately from full-generation peak and steady loaded memory.
4. Qualify single-reference edits, multiple references and actual alpha-channel output separately.
5. Qualify 2048-pixel output and tiled decoding separately, checking seams and detail.
6. Verify repeated requests, cancellation, malformed input, failure, unload and reload.

Report whole-pipeline peak MLX allocation plus process/system memory and swap observations, encoding/denoising/decoding timings, total latency, failures and visual quality. Do not extrapolate a weight-file size or small-image peak to larger images or edits. Start without approximate step skipping, turbo adapters or additional prompt-enhancer models; assess those separately if needed.

Follow `metrics.md` and current AGENTS.md for pilots, monitoring, power conditions, provenance and independent loaded instances. GPU work requires separate authorization and coordination with active campaigns.

## Implementation surfaces

Changes belong in the parent forks before any stack submodule update. Candidate surfaces, not existing image support:

| Surface | Proposed change |
|---|---|
| Parent `mlx-serve` configuration | Image target type and validated runtime/recipe settings |
| Parent `mlx-serve` process manager | Image-worker launch, readiness, unloading, failure recovery and shared scheduling |
| Parent `mlx-serve` router | OpenAI-compatible `/v1/images/generations`, followed by `/v1/images/edits` |
| New image-worker adapter | Qualified MLX pipeline, PNG responses, request validation, cancellation and resource release |
| `main_models.yaml` and configgen | Image recipe source of truth and appropriate exposure in all client emitters; exclude image targets from text-only menus |
| `openwebui-init/init.py` | Apply image configuration through OWUI HTTP API and verify readback |
| `runserver.sh` / stop handling | Supervise any new persistent process; router-owned workers remain router-managed |
| Tests and documentation | Lifecycle/API checks, OWUI end-to-end checks, recipe and operator instructions |

OWUI's OpenAI image engine can point to the local router independently of its chat connection. Generated model JSON must be regenerated, not hand-edited. ComfyUI is an alternative if its workflow ecosystem becomes a requirement; it is not the initial default.

## Acceptance and sequencing

Use failing tests first for new router/worker behavior, mocked workers for inexpensive lifecycle checks, then real standalone and OWUI checks. Acceptance requires:

- OWUI requests, displays and saves the generated image using the configured target.
- Generation, supported edits and alpha survive the API/storage path.
- Chat and image heavyweight workers never overlap, including failure/cancellation paths.
- Repeated switching leaves no orphan workers or growing allocation footprint.
- Returning to chat preserves messages; reload/prefill latency is measured at matched context lengths.
- Task/embedding routing remains functional through switches.
- Restart reconciliation restores and reads back the intended image configuration.
- Selected quantization passes the pre-registered image-quality rubric.

Order: runtime qualification -> image worker and exclusive switching -> generation API -> OWUI generation -> editing/transparency -> repeated-switch and long-context usability assessment -> operator review before deployment defaults change. No implementation or model promotion follows merely from saving this proposal.

## Model licensing

The stack distributes independently written integration/configuration; clients download their own models. Record the upstream Qwen Research License and link it in operator-facing configuration/documentation. Its research/evaluation restriction concerns each operator's model use. The stack's own model use and any actual redistribution of upstream materials have their own obligations. Configuration-only support is not, by itself, model-weight redistribution.

## Sources

- [Official model card](https://huggingface.co/Qwen/Qwen-Image-2.1)
- [MLX 4-bit checkpoint](https://huggingface.co/mlx-community/Qwen-Image-2.1-MLX-4bit/tree/main)
- [MFLUX reference/editing path](https://github.com/mflux-community/mflux/blob/main/src/mflux/models/qwen21/reference/README.md)
- [MFLUX validation and limitations](https://github.com/mflux-community/mflux/blob/main/src/mflux/models/qwen21/reference/VALIDATION.md)
- [OWUI OpenAI-compatible image integration](https://docs.openwebui.com/features/chat-conversations/image-generation-and-editing/openai/)
- [Model license](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)

## Review 2026-10-04 (Claude Fable 5.1; the proposal above was produced by GPT-Astra) <!-- allow-shorthand -->

**Verdict: keep deferred (operator decision 2026-10-04).** The architecture is sound and consistent with the stack's rules; the
corrections below are for whenever it is picked up.

1. **The exclusive heavyweight slot already exists in practice.** The stack runs ONE resident model per machine and unloads between
   models (AGENTS.md); the router's unload/load lifecycle is the mechanism this proposal needs. What is new is a non-chat worker type and
   the `/v1/images/*` routes, not the scheduling model. Reuse the existing process manager rather than designing a second lock.
2. **The switch cost is the real product question, and it is large.** Returning to chat after an image request means a model reload and a
   full re-prefill of the conversation. At the first pick's deployed native16 configuration that is minutes to tens of minutes for a
   long context (prefill is the quadratic term; see the flash-attention review for the only lever that shrinks it). The proposal says
   "measure it"; the stronger statement is that automatic switching inside one OpenWebUI conversation will not be acceptable at long
   context, so the design should default to an explicit operator-initiated switch (a separate OWUI model entry for image work, or a
   "chat is unloaded while image generation is active" banner), not transparent routing.
3. **Capacity numbers.** 10.5 GB is the `mlx-community/Qwen-Image-2.1-MLX-4bit` checkpoint on disk. The first pick resident with full-cap native16 KV preallocation is
   ~17 GB of weights plus ~10–16 GB per retained session (C108), so co-residency is ruled out by preallocation policy, not only by peaks;
   the swap design is the correct one and should stay that way unless the operator relaxes the prealloc rule for a reduced-context
   "image-session" chat profile — which would be a new (model, tune) triple needing its own certification.
4. **Verify the pipeline composition before sizing anything.** "Roughly 8B text/vision encoder" matches the Qwen-Image family's use of a
   Qwen2.5-VL-class encoder, but the exact encoder for `Qwen/Qwen-Image-2.1` and whether MFLUX's reference path quantizes it were not
   verified in this session; treat the storage table as provisional.
5. **Rules that already apply and should be cited in the spec:** OWUI settings are live only via `init.py` through the HTTP API (C98), so
   the image engine configuration must be applied and read back there; generated model JSON is regenerated by `configgen`, never
   hand-edited; artifacts and caches stay under `$STACK_WORKDIR` or the pre-approved caches; any GPU qualification runs on a quiet box
   with the laptop power gate (140 W / battery > 20 %) and k=2 sessions where sampling is unseeded.
6. **Licensing paragraph is fine as written.** Keep the configuration-only stance; do not vendor weights.

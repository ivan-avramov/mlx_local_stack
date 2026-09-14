# OpenCode config for mlx_local_stack

`opencode.json` is generated from [main_models.yaml](../main_models.yaml). Change the registry, then run `uv run python -m configgen generate`; `uv run python -m configgen check` checks all generated carriers. Keep personal additions in your installed config rather than in generated files.

The `mlx-local` provider uses `http://localhost:8000/v1`. It advertises the seven registry entries with `presentation.role: main`; candidates are available only in the benchmark carrier. The default is `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; `Qwen3.8-27B-mlx-uniform-4bit` is the second approved pick. See the root README for current ranking and evidence.

All seven main models support tools and thinking. `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` is text-only, so its `attachment` flag is false; the other six main registrations advertise vision. The separate `mlx-task` provider points to `http://localhost:8092/v1` and supplies the text-only `mlx-community/Qwen2.5-1.5B-Instruct-4bit` small model. Switching main models can reload the router's single resident model.

Vision registrations also declare `modalities.input: ["text", "image"]`; text-only registrations, including the task model, declare `["text"]`. Every registration declares text output. OpenCode v1.18.30 [accepts these fields](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/core/src/v1/config/provider.ts#L52-L59) and [resolves image support independently of `attachment`](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/provider/provider.ts#L1427-L1447). Without explicit image input, a custom vision model's image parts can be replaced with an unsupported-input error before reaching the server.

## Install and select

1. Start the stack when you intend to use these clients; do not interrupt an active benchmark.
2. Merge `opencode.json` into your project config or `~/.config/opencode/opencode.json`.
3. The local API key is `not-needed`; register that placeholder if your client requires provider authentication.
4. Restart OpenCode after changing its config. Select a model with `/models` or `--model mlx-local/<full-registry-name>`.

The task-model reference contains two slashes: `mlx-task/mlx-community/Qwen2.5-1.5B-Instruct-4bit`. The first component is the provider; the rest is the exact model ID.

## Limits and sampling

| Field | Registry mapping |
|---|---|
| `limit.context` | Full context window |
| `limit.input` | Context window minus output ceiling |
| `limit.output` | Output ceiling |
| `options` | Family-supported sampling and thinking parameters |

For both approved picks, these limits are 262144 context, 159744 input, and 102400 output tokens. OpenCode also reserves compaction headroom. Its [v1.18.30 overflow calculation](https://github.com/anomalyco/opencode/blob/v1.18.30/packages/opencode/src/session/overflow.ts) treats context as the full window and handles an explicit input limit separately; supplying the input budget as context would subtract output space twice.

Both approved picks carry `top_p: 0.95`, `top_k: 20`, `min_p: 0`, `presence_penalty: 0`, `thinking_budget: 81920`, and `enable_thinking: true`. Their temperatures are 0.5 and 0.6 respectively. The registry's `reasoning_effort: medium` applies when the client omits that field. Other models retain their own registry settings; family filtering does not invent unsupported sampling keys.

KV format, MTP configuration, cache retirement, and full-cap allocation belong to the server registry. They are not client options. This config retains the installed OpenCode v1 format; it is not a v2 migration.

## Prior transport validation

The P1a smoke on OpenCode 1.18.15 (2026-08-13) verified requests reaching the router and forwarding of `max_tokens`, `thinking_budget`, and `enable_thinking`. See [campaign results](../docs/campaign-results.md). Those measurements are historical; this config audit did not run a new client request.

OpenCode rejects unknown top-level config keys. A previous `_generated` marker prevented the entire config from loading, which is why provenance lives in this README. Check config-validation errors before diagnosing the serving endpoint.

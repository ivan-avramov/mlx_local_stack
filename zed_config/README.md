# Zed config for mlx_local_stack

`settings.snippet.jsonc` is generated from [main_models.yaml](../main_models.yaml). Regenerate with `uv run python -m configgen generate` and check with `uv run python -m configgen check`.

The snippet registers the seven `presentation.role: main` models at `http://localhost:8000/v1`. Candidates and the separate task model are not included. It contains no `agent` block or model default: choose a model in Zed. The first approved pick is `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, followed by `Qwen3.8-27B-mlx-uniform-4bit`; see the root README for current ranking and evidence.

## Install

1. Start the stack when you intend to use the client; preserve active benchmark jobs.
2. Open Zed's settings JSON and merge `language_models.openai_compatible.mlx-local` from the snippet. Preserve your other settings.
3. Configure the `mlx-local` provider in the Agent panel and supply `not-needed` if it requests an API key. A provider without a registered key may remain hidden from the model picker.
4. Select a model under `mlx-local`.

Per-role selections are personal Zed settings. The generated snippet does not pin a title, summary, commit-message, or subagent model.

## Registration and server defaults

| Field | Meaning |
|---|---|
| `max_tokens` | Full context window |
| `max_output_tokens` | Output ceiling |
| `interleaved_reasoning` | Reasoning presentation capability |
| `capabilities` | Tools, image input, parallel tool calls, and cache-key support |

Both approved picks declare a 262144-token context window and 102400-token output ceiling. `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` has `images: false`; the other six main models have `images: true`. All main entries advertise tools and reasoning. The snippet includes every capability field expected by its current schema.

This is a registration-only carrier: it does not emit sampling controls. Omitted request fields receive the registry's `generation_defaults`, including `enable_thinking`, `thinking_budget`, and each model's sampling. Both approved picks use thinking budget 81920 and `reasoning_effort: medium`, with temperatures 0.5 and 0.6 respectively. Personal client overrides can supersede those defaults.

KV format, MTP, cache retirement, and full-cap allocation remain server settings. `prompt_cache_key: false` does not disable the stack's server-side session cache. This audit checked the generated snippet against the registry; it did not run a new Zed request.

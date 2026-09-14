# VS Code Copilot config for mlx_local_stack

`chatLanguageModels.json` is generated from [main_models.yaml](../main_models.yaml). Regenerate with `uv run python -m configgen generate` and check with `uv run python -m configgen check`.

The Custom Endpoint provider registers the seven `presentation.role: main` models at `http://localhost:8000/v1/chat/completions`. Candidates and the separate task model are excluded. No model selection is generated; choose one in Copilot Chat. The first approved pick is `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, followed by `Qwen3.8-27B-mlx-uniform-4bit`; see the root README for ranking and evidence.

## Install

Custom Endpoint is available in VS Code Stable as of [version 1.122](https://code.visualstudio.com/updates/v1_122). The earlier Insiders-only guidance is obsolete. Organization policy can still restrict BYOK; consult [VS Code's language-model documentation](https://code.visualstudio.com/docs/agent-customization/language-models).

1. Start the stack when you intend to use the client; do not interrupt active benchmark jobs.
2. Open **Chat: Manage Language Models**, choose **Add Models → Custom Endpoint**, and select **Chat Completions**.
3. Merge this folder's provider/model entries into the configuration VS Code opens, preserving existing providers.
4. Supply `not-needed` if an API key is required by the client.
5. Select a registered `mlx-local` model in Copilot Chat.

## Limits, capabilities, and sampling

| Field | Registry mapping |
|---|---|
| `maxInputTokens` | Full context window minus output ceiling |
| `maxOutputTokens` | Output ceiling |
| `toolCalling` / `thinking` | Main models' tool and reasoning capabilities |
| `vision` | The model's registry vision capability |

Both approved picks declare 159744 input tokens and 102400 output tokens, totaling their 262144-token context window. `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` is text-only and has `vision: false`; the other six main registrations have `vision: true`.

This is a registration-only carrier. The generated file does not send sampling or thinking-budget overrides. The server fills omitted fields from `generation_defaults`: both approved picks use thinking budget 81920 and `reasoning_effort: medium`, with temperatures 0.5 and 0.6 respectively. The `thinking` flag describes reasoning support; it does not itself choose a thinking budget.

KV format, MTP, full-cap allocation, and cache retirement are server configuration. This file does not assign separate utility-model roles; any personal VS Code role settings remain outside the generated carrier. A model switch may reload the router's resident model.

This audit verified registry/config consistency. It did not perform a new Copilot agent-edit or streaming-tool test.
